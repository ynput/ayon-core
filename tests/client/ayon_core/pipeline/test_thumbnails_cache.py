"""Tests for thumbnails cache on local storage."""

from __future__ import annotations

import os
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ayon_core.pipeline import thumbnails


@pytest.fixture
def cache(tmp_path, monkeypatch):
    cache = thumbnails.ThumbnailsCache(cleanup=False)
    # 'tmp_path' may be shared by more tests
    cache._thumbnails_dir = tempfile.mkdtemp(dir=str(tmp_path))
    monkeypatch.setattr(thumbnails._CacheItems, "thumbnails_cache", cache)
    return cache


def test_store_thumbnail_does_not_leave_temp_files(cache):
    path = cache.store_thumbnail("demo", "thumbnail-id", b"data", "image/png")

    assert cache.get_thumbnail_filepath("demo", "thumbnail-id") == path
    assert os.listdir(os.path.dirname(path)) == ["thumbnail-id.png"]
    with open(path, "rb") as stream:
        assert stream.read() == b"data"


def test_store_thumbnail_that_is_already_stored_and_used(cache, monkeypatch):
    path = cache.store_thumbnail("demo", "thumbnail-id", b"data", "image/png")
    # On Windows a file that is opened by other process cannot be replaced
    monkeypatch.setattr(
        thumbnails.os, "replace", Mock(side_effect=PermissionError())
    )

    assert (
        cache.store_thumbnail("demo", "thumbnail-id", b"data", "image/png")
        == path
    )
    assert os.listdir(os.path.dirname(path)) == ["thumbnail-id.png"]


def test_failed_store_of_new_thumbnail_is_raised(cache, monkeypatch):
    monkeypatch.setattr(
        thumbnails.os, "replace", Mock(side_effect=PermissionError())
    )

    with pytest.raises(PermissionError):
        cache.store_thumbnail("demo", "thumbnail-id", b"data", "image/png")
    assert os.listdir(cache.get_project_dir("demo")) == []


def test_cleanup_skips_files_that_cannot_be_removed(cache, monkeypatch):
    old_time = time.time() - (cache.days_alive * 24 * 60 * 60) - 60
    paths = []
    for thumbnail_id in ("used", "unused"):
        path = cache.store_thumbnail(
            "demo", thumbnail_id, b"data", "image/png"
        )
        os.utime(path, (old_time, old_time))
        paths.append(path)

    remove = os.remove

    def _remove(path):
        if path == paths[0]:
            raise PermissionError()
        remove(path)

    monkeypatch.setattr(thumbnails.os, "remove", _remove)
    cache.cleanup()

    assert os.path.exists(paths[0])
    assert not os.path.exists(paths[1])


def test_thumbnail_is_stored_by_id_from_server(cache, monkeypatch):
    """Entity could receive a new thumbnail since its id was queried."""
    con = Mock()
    con.get_thumbnail.return_value = SimpleNamespace(
        is_valid=True,
        thumbnail_id="new-id",
        content=b"new",
        content_type="image/jpeg",
    )
    monkeypatch.setattr(
        thumbnails.ayon_api, "get_server_api_connection", lambda: con
    )

    path = thumbnails.get_thumbnail_path("demo", "folder", "folder", "old-id")

    assert path == cache.get_thumbnail_filepath("demo", "new-id")
    assert cache.get_thumbnail_filepath("demo", "old-id") is None

    # Cached thumbnail is not requested again
    assert thumbnails.get_thumbnail_path(
        "demo", "folder", "folder", "new-id"
    ) == path
    assert con.get_thumbnail.call_count == 1
