"""Tests for the cache of user avatars on local storage."""

from __future__ import annotations

import os
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_core.pipeline import avatars


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch, tmp_path) -> dict[str, Any]:
    """Server with an avatar for 'roy' only, and an empty avatars cache."""
    state: dict[str, Any] = {"calls": [], "url": "https://ayon.one"}
    # 'tmp_path' is not unique for each test in this repository
    cache_dir = tmp_path / uuid.uuid4().hex

    def raw_get(endpoint: str):
        state["calls"].append(endpoint)
        if endpoint == "users/roy/avatar":
            return SimpleNamespace(
                status_code=200, content=b"png", content_type="image/png"
            )
        return SimpleNamespace(
            status_code=404, content=b"{}", content_type="application/json"
        )

    monkeypatch.setattr(
        avatars.ayon_api,
        "get_server_api_connection",
        lambda: SimpleNamespace(raw_get=raw_get),
    )
    monkeypatch.setattr(avatars.ayon_api, "get_base_url", lambda: state["url"])
    monkeypatch.setattr(
        avatars,
        "get_launcher_local_dir",
        lambda *subdirs: os.path.join(str(cache_dir), *subdirs),
    )
    monkeypatch.setattr(
        avatars._CacheItems, "avatars_cache", avatars.AvatarsCache()
    )
    return state


def test_avatar_is_downloaded_once(fake_server):
    path = avatars.get_user_avatar_path("roy")

    assert path.endswith("roy.png")
    with open(path, "rb") as stream:
        assert stream.read() == b"png"
    assert avatars.get_user_avatar_path("roy") == path
    assert fake_server["calls"] == ["users/roy/avatar"]


def test_avatar_is_shared_with_other_processes(fake_server, monkeypatch):
    path = avatars.get_user_avatar_path("roy")

    # Another process has its own cache object over the same directory
    monkeypatch.setattr(
        avatars._CacheItems, "avatars_cache", avatars.AvatarsCache()
    )
    assert avatars.get_user_avatar_path("roy") == path
    assert fake_server["calls"] == ["users/roy/avatar"]


def test_user_without_avatar_is_remembered(fake_server):
    assert avatars.get_user_avatar_path("libor") is None
    assert avatars.get_user_avatar_path("libor") is None
    assert fake_server["calls"] == ["users/libor/avatar"]
    assert avatars.get_user_avatar_path("") is None


def test_avatar_is_downloaded_again_after_its_lifetime(fake_server):
    path = avatars.get_user_avatar_path("roy")
    expired = time.time() - avatars.AvatarsCache.lifetime - 60
    os.utime(path, (expired, expired))

    assert avatars.get_user_avatar_path("roy") == path
    assert len(fake_server["calls"]) == 2


def test_avatars_are_stored_per_server(fake_server, monkeypatch):
    path = avatars.get_user_avatar_path("roy")

    fake_server["url"] = "https://ayon.two"
    monkeypatch.setattr(
        avatars._CacheItems, "avatars_cache", avatars.AvatarsCache()
    )
    other_path = avatars.get_user_avatar_path("roy")
    assert other_path != path
    assert len(fake_server["calls"]) == 2


def test_username_can_not_leave_the_cache_directory(fake_server):
    cache = avatars._CacheItems.avatars_cache
    base_path = cache._get_base_path("../../evil/name")

    assert os.path.dirname(base_path) == cache.get_avatars_dir()
