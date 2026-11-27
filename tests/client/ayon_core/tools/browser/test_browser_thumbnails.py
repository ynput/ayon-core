"""Tests for the thumbnail loading of the Browser."""

from __future__ import annotations

import tempfile
from types import SimpleNamespace

import pytest

from ayon_core.tools.browser.ui import _browser_thumbnails
from ayon_core.ui import image_cache


@pytest.mark.parametrize(
    "content_type, ext",
    [("image/jpeg", ".jpg"), ("image/png", ".png")],
)
def test_thumbnail_is_cached_without_temp_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
    content_type: str,
    ext: str,
) -> None:
    """The downloaded thumbnail is passed to the image cache from memory."""
    temp_dir = tmp_path_factory.mktemp("temp")
    cache_dir = tmp_path_factory.mktemp("cache")
    # Bypass the singleton of the image cache
    cache = object.__new__(image_cache.ImageCache)
    cache._initialize(cache_dir, 10)
    calls = []

    def _get_version_thumbnail(*args: str) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(
            is_valid=True,
            content=b"image data",
            content_type=content_type,
        )

    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    monkeypatch.setattr(
        _browser_thumbnails.ayon_api,
        "get_version_thumbnail",
        _get_version_thumbnail,
    )
    monkeypatch.setattr(
        _browser_thumbnails.ImageCache,
        "get_instance",
        classmethod(lambda cls: cache),
    )

    try:
        path = _browser_thumbnails._thumbnail_loader(
            "project/version_id/thumbnail_id"
        )
    finally:
        cache._close_all_connections()

    assert calls == [("project", "version_id", "thumbnail_id")]
    assert list(temp_dir.iterdir()) == []
    cached_paths = list(cache_dir.glob(f"*{ext}"))
    assert [str(cached_path) for cached_path in cached_paths] == [path]
    assert cached_paths[0].read_bytes() == b"image data"
