"""Tests for downloading user avatars."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

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
    tmp_path: Path,
    content: bytes,
    content_type: str,
) -> str:
    connection = FakeConnection(FakeResponse(content, content_type))
    monkeypatch.setattr(
        user_avatars.ayon_api,
        "get_server_api_connection",
        lambda: connection,
    )
    monkeypatch.setattr(user_avatars.tempfile, "tempdir", str(tmp_path))
    path = user_avatars._fetch_avatar_file("kuba")
    assert connection.urls == ["users/kuba/avatar"]
    return path


def test_uploaded_avatar_is_saved_to_a_file(monkeypatch, tmp_path):
    path = _fetch(monkeypatch, tmp_path, b"jpeg data", "image/jpeg")

    assert Path(path).suffix == ".jpg"
    assert Path(path).read_bytes() == b"jpeg data"


def test_uploaded_svg_avatar_is_kept(monkeypatch, tmp_path):
    path = _fetch(
        monkeypatch, tmp_path, UPLOADED_SVG_AVATAR, "image/svg+xml"
    )

    assert Path(path).read_bytes() == UPLOADED_SVG_AVATAR


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
    monkeypatch, tmp_path, content, content_type
):
    # Initials are rendered locally for such user
    assert _fetch(monkeypatch, tmp_path, content, content_type) == ""
    assert list(tmp_path.iterdir()) == []


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
def test_downloaded_temp_file_is_removed(monkeypatch, tmp_path, copy_fails):
    """The download is removed once the image cache has its own copy."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sources: list[Path] = []

    class FakeImageCache:
        def get(self, key: str, file_closure: Any) -> str:
            source = Path(file_closure())
            sources.append(source)
            assert source.read_bytes() == b"jpeg data"
            if copy_fails:
                raise OSError("Disk is full")
            cached_path = cache_dir / source.name
            shutil.copyfile(source, cached_path)
            return str(cached_path)

    class FakeQueue:
        def enqueue(self, task: Any) -> None:
            task.callback(task.function())

    connection = FakeConnection(FakeResponse(b"jpeg data", "image/jpeg"))
    monkeypatch.setattr(
        user_avatars.ayon_api,
        "get_server_api_connection",
        lambda: connection,
    )
    monkeypatch.setattr(user_avatars.tempfile, "tempdir", str(temp_dir))
    monkeypatch.setattr(
        user_avatars.ImageCache,
        "get_instance",
        classmethod(lambda cls: FakeImageCache()),
    )
    monkeypatch.setattr(user_avatars, "get_task_queue", FakeQueue)
    cache = user_avatars.UserAvatarCache()

    assert cache.pixmap("kuba", "Kuba Trllo", 20) is not None
    app.processEvents()

    # The file was downloaded, and only the cached copy is left
    assert len(sources) == 1
    assert list(temp_dir.iterdir()) == []
    if copy_fails:
        assert cache._sources == {"kuba": ""}
    else:
        cached_path = cache_dir / sources[0].name
        assert cache._sources == {"kuba": str(cached_path)}
        assert cached_path.read_bytes() == b"jpeg data"
