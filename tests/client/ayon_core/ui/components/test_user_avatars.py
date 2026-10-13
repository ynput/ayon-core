"""Tests for downloading user avatars."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ayon_core.ui import image_cache
from ayon_core.ui.components import user_avatars

# What the server responds with for a user without an avatar
SVG_AVATAR = b"""<svg width="100px" height="100px" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#487957"/>
      <text
        x="50%"
        y="50%"
        dominant-baseline="central"
        text-anchor="middle"
        fill="white"
        font-size="50px"
        font-family="Arial"
      >
        KT
      </text>
    </svg>"""
UPLOADED_SVG_AVATAR = (
    b'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">'
    b'<circle cx="50" cy="50" r="40" fill="red"/></svg>'
)


class FakeResponse:
    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.content_type = content_type


class FakeConnection:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.urls: list[str] = []

    def raw_get(self, url: str) -> Any:
        self.urls.append(url)
        return self.response


def _fetch(
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    content_type: str,
) -> io.BytesIO | None:
    connection = FakeConnection(FakeResponse(content, content_type))
    monkeypatch.setattr(
        user_avatars.ayon_api,
        "get_server_api_connection",
        lambda: connection,
    )
    stream = user_avatars._fetch_avatar("kuba")
    assert connection.urls == ["users/kuba/avatar"]
    return stream


def test_uploaded_avatar_is_downloaded_to_memory(monkeypatch):
    stream = _fetch(monkeypatch, b"jpeg data", "image/jpeg")

    assert Path(stream.name).suffix == ".jpg"
    assert stream.getvalue() == b"jpeg data"


def test_uploaded_svg_avatar_is_kept(monkeypatch):
    stream = _fetch(monkeypatch, UPLOADED_SVG_AVATAR, "image/svg+xml")

    assert stream.getvalue() == UPLOADED_SVG_AVATAR


@pytest.mark.parametrize(
    "content, content_type",
    [
        (SVG_AVATAR, "image/svg+xml"),
        # Content type is not always filled
        (SVG_AVATAR, ""),
        (b"", "image/png"),
    ],
    ids=["initials", "initials_without_content_type", "empty"],
)
def test_generated_initials_are_not_used_as_avatar(
    monkeypatch, content, content_type
):
    # Initials are rendered locally for such user
    assert _fetch(monkeypatch, content, content_type) is None


def test_cached_generated_initials_are_ignored(monkeypatch, tmp_path):
    """Initials cached before they were skipped are not displayed."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cached_path = tmp_path / "cached.png"
    cached_path.write_bytes(SVG_AVATAR)

    class FakeImageCache:
        def get(self, key: str, file_closure: Any) -> str:
            return str(cached_path)

    class FakeQueue:
        def enqueue(self, task: Any) -> None:
            task.callback(task.function())

    monkeypatch.setattr(
        user_avatars.ImageCache,
        "get_instance",
        classmethod(lambda cls: FakeImageCache()),
    )
    monkeypatch.setattr(user_avatars, "get_task_queue", FakeQueue)
    cache = user_avatars.UserAvatarCache()
    updated: list[str] = []
    cache.avatar_updated.connect(updated.append)

    assert cache.pixmap("kuba", "Kuba Trllo", 20) is not None
    app.processEvents()

    # The miss is remembered and the initials placeholder is kept
    assert cache._sources == {"kuba": ""}
    assert updated == []


@pytest.mark.parametrize("copy_fails", [False, True], ids=["copied", "failed"])
def test_avatar_is_cached_without_temp_file(monkeypatch, tmp_path, copy_fails):
    """The download is passed to the image cache from memory."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    cache_dir = tmp_path / "cache"
    # Bypass the singleton of the image cache
    cache_instance = object.__new__(image_cache.ImageCache)
    cache_instance._initialize(cache_dir, 10)

    class FakeQueue:
        def enqueue(self, task: Any) -> None:
            task.callback(task.function())

    def _fail_copy(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("Disk is full")

    connection = FakeConnection(FakeResponse(b"jpeg data", "image/jpeg"))
    monkeypatch.setattr(
        user_avatars.ayon_api,
        "get_server_api_connection",
        lambda: connection,
    )
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    monkeypatch.setattr(
        user_avatars.ImageCache,
        "get_instance",
        classmethod(lambda cls: cache_instance),
    )
    if copy_fails:
        monkeypatch.setattr(image_cache.shutil, "copyfileobj", _fail_copy)
    monkeypatch.setattr(user_avatars, "get_task_queue", FakeQueue)
    cache = user_avatars.UserAvatarCache()

    try:
        assert cache.pixmap("kuba", "Kuba Trllo", 20) is not None
        app.processEvents()
    finally:
        cache_instance._close_all_connections()

    # The avatar was downloaded, and only the cached copy is on disk
    assert connection.urls == ["users/kuba/avatar"]
    assert list(temp_dir.iterdir()) == []
    assert list(cache_dir.glob("*.tmp")) == []
    cached_paths = list(cache_dir.glob("*.jpg"))
    if copy_fails:
        assert cached_paths == []
        assert cache._sources == {"kuba": ""}
    else:
        assert len(cached_paths) == 1
        assert cache._sources == {"kuba": str(cached_paths[0])}
        assert cached_paths[0].read_bytes() == b"jpeg data"


def test_user_without_avatar_is_not_cached(monkeypatch):
    """Nothing is passed to the image cache for a user without avatar."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class FakeImageCache:
        def get(self, key: str, file_closure: Any) -> str:
            file_closure()
            raise AssertionError("Closure should not return")

    class FakeQueue:
        def enqueue(self, task: Any) -> None:
            task.callback(task.function())

    connection = FakeConnection(FakeResponse(SVG_AVATAR, "image/svg+xml"))
    monkeypatch.setattr(
        user_avatars.ayon_api,
        "get_server_api_connection",
        lambda: connection,
    )
    monkeypatch.setattr(
        user_avatars.ImageCache,
        "get_instance",
        classmethod(lambda cls: FakeImageCache()),
    )
    monkeypatch.setattr(user_avatars, "get_task_queue", FakeQueue)
    cache = user_avatars.UserAvatarCache()

    assert cache.pixmap("kuba", "Kuba Trllo", 20) is not None
    app.processEvents()

    # The miss is remembered and the initials placeholder is kept
    assert connection.urls == ["users/kuba/avatar"]
    assert cache._sources == {"kuba": ""}


def test_cached_avatar_is_read_while_other_process_stores_it(
    monkeypatch, tmp_path
):
    """On Windows a file cannot be opened while it is being replaced."""
    avatar_path = tmp_path / "avatar.png"
    avatar_path.write_bytes(b"png data")
    attempts: list[str] = []

    def open_file_in_use(file_path: str, mode: str) -> Any:
        attempts.append(file_path)
        if len(attempts) < 3:
            raise PermissionError(13, "Permission denied", file_path)
        return open(file_path, mode)

    monkeypatch.setattr(
        user_avatars, "open", open_file_in_use, raising=False
    )
    monkeypatch.setattr(user_avatars.time, "sleep", lambda _seconds: None)

    assert user_avatars._read_file_head(str(avatar_path)) == b"png data"
    assert len(attempts) == 3


def test_avatar_removed_by_other_process_is_downloaded_again(
    monkeypatch, tmp_path
):
    """The image cache is shared, other process can evict the file."""
    from qtpy import QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    image = QtGui.QImage(32, 32, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("red"))
    avatar_path = str(tmp_path / "avatar.png")
    assert image.save(avatar_path)

    class FakeImageCache:
        def get(self, key: str, file_closure: Any) -> str:
            return avatar_path

    tasks: list[Any] = []

    class ManualQueue:
        def enqueue(self, task: Any) -> None:
            tasks.append(task)

    monkeypatch.setattr(
        user_avatars.ImageCache,
        "get_instance",
        classmethod(lambda cls: FakeImageCache()),
    )
    monkeypatch.setattr(user_avatars, "get_task_queue", ManualQueue)
    cache = user_avatars.UserAvatarCache()
    cache._sources["kuba"] = str(tmp_path / "evicted.png")

    # Initials are shown instead of an empty image
    pixmap = cache.pixmap("kuba", "Kuba Trllo", 20)
    color = pixmap.toImage().pixelColor(2, pixmap.height() // 2)
    assert color.alpha() > 0
    assert "kuba" not in cache._sources

    # The avatar is downloaded again
    assert len(tasks) == 1
    task = tasks.pop()
    task.callback(task.function())
    app.processEvents()
    assert cache._sources == {"kuba": avatar_path}
