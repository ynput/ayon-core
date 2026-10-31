"""Tests for 'LocalPreferences' and 'UserPreferences'."""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import ayon_api
import pytest

from ayon_core.lib import (
    JSONSettingRegistry,
    LocalPreferences,
    UserPreferences,
    UserPreferencesNotSupported,
    get_launcher_local_dir,
)
from ayon_core.lib import preferences
from ayon_core.lib.local_settings import RegistryItemNotFound

KEY = "io.ynput.core.tests"


class FakeResponse:
    def __init__(self, status_code: int, data: Optional[dict] = None):
        self.status_code = status_code
        self.data = data or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def detail(self) -> str:
        return self.data.get("detail", "")


class FakeServer:
    """Preferences API of AYON server, as in ayon-backend#1231.

    Args:
        status_code: Status code of every request instead of handling it,
            e.g. 404 of a server without the API.

    """
    def __init__(self, status_code: Optional[int] = None) -> None:
        self.status_code = status_code
        # Data by (key, project name)
        self.preferences: dict[tuple[str, Optional[str]], dict] = {}
        self.calls: list[tuple[str, str, Optional[str], Any]] = []

    def raw_get(self, endpoint: str, **kwargs) -> FakeResponse:
        return self._handle("get", endpoint, kwargs)

    def raw_put(self, endpoint: str, **kwargs) -> FakeResponse:
        return self._handle("put", endpoint, kwargs)

    def raw_patch(self, endpoint: str, **kwargs) -> FakeResponse:
        return self._handle("patch", endpoint, kwargs)

    def raw_delete(self, endpoint: str, **kwargs) -> FakeResponse:
        return self._handle("delete", endpoint, kwargs)

    def _handle(self, method: str, endpoint: str, kwargs) -> FakeResponse:
        parsed = urlparse(endpoint)
        query = {
            name: values[0] for name, values in parse_qs(parsed.query).items()
        }
        project_name = query.get("project_name")
        body = kwargs.get("json")
        self.calls.append((method, parsed.path, project_name, body))
        if self.status_code is not None:
            return FakeResponse(self.status_code, {"detail": "Failed"})

        if parsed.path == "preferences" and method == "get":
            prefix = query.get("key_prefix", "")
            # Data are copied like JSON of a response would be
            return FakeResponse(200, {"preferences": [
                {
                    "key": key,
                    "projectName": project,
                    "data": copy.deepcopy(data),
                }
                for (key, project), data in self.preferences.items()
                if project == project_name and key.startswith(prefix)
            ]})

        key = parsed.path.split("/", 1)[1]
        scope = (key, project_name)
        if method == "put":
            self.preferences[scope] = dict(body)
        elif method == "patch":
            self.preferences.setdefault(scope, {}).update(body)
        elif method == "delete":
            if self.preferences.pop(scope, None) is None:
                return FakeResponse(404, {"detail": "Not found"})
        return FakeResponse(204)


@pytest.fixture(autouse=True)
def local_dir(tmp_path_factory, monkeypatch) -> str:
    # 'tmp_path' of pytest-ayon is shared by the whole session
    tmp_path = tmp_path_factory.mktemp("local_dir")
    monkeypatch.setenv("AYON_LAUNCHER_LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        ayon_api, "get_base_url", lambda: "http://ayon.server"
    )
    monkeypatch.setattr(preferences._ServerSupport, "by_url", {})
    return str(tmp_path)


def use_server(monkeypatch, server: FakeServer) -> FakeServer:
    for method in ("get", "put", "patch", "delete"):
        name = f"raw_{method}"
        monkeypatch.setattr(ayon_api, name, getattr(server, name))
    return server


def read_json(path: str) -> dict:
    with open(path, "r") as stream:
        return json.load(stream)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name", ["", "a/b", "..", ".hidden", "trailing.", "a b", "x" * 129]
)
def test_invalid_names_are_refused(name):
    with pytest.raises(ValueError):
        LocalPreferences(name)
    with pytest.raises(ValueError):
        UserPreferences(name)


@pytest.mark.unit
def test_local_preferences_items(local_dir):
    prefs = LocalPreferences(KEY)

    assert prefs.filepath == os.path.join(local_dir, "tools", f"{KEY}.json")
    assert prefs.get_item("sizes", default=[]) == []
    with pytest.raises(RegistryItemNotFound):
        prefs.get_item("sizes")
    # Nothing is written until an item is set
    assert not os.path.exists(prefs.filepath)

    prefs.set_item("sizes", [200, 400])
    prefs.set_item("visible", True)
    assert LocalPreferences(KEY).get_item("sizes") == [200, 400]
    assert prefs.get_data() == {"sizes": [200, 400], "visible": True}

    prefs.delete_item("sizes")
    prefs.delete_item("missing")
    with pytest.raises(RegistryItemNotFound):
        prefs.delete_item("missing", ignore_missing=False)
    assert LocalPreferences(KEY).get_data() == {"visible": True}

    prefs.clear()
    assert not os.path.exists(prefs.filepath)


@pytest.mark.unit
def test_local_preferences_use_existing_registry():
    """Registries of tools are read and written without conversion."""
    registry = JSONSettingRegistry("launcher", get_launcher_local_dir("tools"))
    registry.set_item("grouped_hosts", '["maya"]')

    prefs = LocalPreferences("launcher")
    assert prefs.filepath == registry.filepath
    assert prefs.get_item("grouped_hosts") == '["maya"]'

    prefs.set_item("grouped_hosts", '["maya", "nuke"]')
    content = read_json(registry.filepath)
    assert "__metadata__" in content
    # A new registry, the old one caches what it read
    registry = JSONSettingRegistry("launcher", get_launcher_local_dir("tools"))
    assert registry.get_item("grouped_hosts") == '["maya", "nuke"]'


@pytest.mark.unit
def test_local_preferences_ignore_a_broken_file():
    prefs = LocalPreferences(KEY)
    os.makedirs(os.path.dirname(prefs.filepath))
    with open(prefs.filepath, "w") as stream:
        stream.write("{not json")

    assert prefs.get_item("visible", default=False) is False
    prefs.set_item("visible", True)
    assert prefs.get_item("visible") is True


@pytest.mark.unit
def test_user_preferences_are_stored_on_server(monkeypatch):
    server = use_server(monkeypatch, FakeServer())
    server.preferences[(KEY, None)] = {"visible": True}
    server.preferences[(f"{KEY}.other", None)] = {"visible": False}

    prefs = UserPreferences(KEY)
    assert prefs.get_item("visible") is True
    assert prefs.get_item("sizes", default=None) is None
    # Received once, cached since. That also told the server has the API.
    assert UserPreferences.is_supported() is True
    assert server.calls == [("get", "preferences", None, None)]

    prefs.set_item("sizes", [1, 2])
    # Only the changed item is sent, the server merges it
    assert server.calls[-1] == ("patch", f"preferences/{KEY}", None, {
        "sizes": [1, 2]
    })
    assert server.preferences[(KEY, None)] == {
        "visible": True, "sizes": [1, 2]
    }
    assert prefs.get_item("sizes") == [1, 2]


@pytest.mark.unit
def test_user_preferences_of_project(monkeypatch):
    server = use_server(monkeypatch, FakeServer())
    server.preferences[(KEY, None)] = {"visible": True}

    prefs = UserPreferences(KEY, project_name="demo")
    assert prefs.get_item("visible", default=False) is False

    prefs.set_item("visible", True)
    assert server.calls[-1][2] == "demo"
    assert server.preferences[(KEY, "demo")] == {"visible": True}


@pytest.mark.unit
def test_user_preferences_refresh(monkeypatch):
    server = use_server(monkeypatch, FakeServer())
    prefs = UserPreferences(KEY)
    assert prefs.get_data() == {}

    # Changed on another machine
    server.preferences[(KEY, None)] = {"visible": True}
    assert prefs.get_data() == {}
    assert prefs.refresh() is True
    assert prefs.get_data() == {"visible": True}


@pytest.mark.unit
def test_user_preferences_delete_keeps_items_of_others(monkeypatch):
    server = use_server(monkeypatch, FakeServer())
    server.preferences[(KEY, None)] = {"visible": True, "sizes": [1]}
    prefs = UserPreferences(KEY)
    assert prefs.get_item("sizes") == [1]

    # Changed by another process meanwhile
    server.preferences[(KEY, None)]["other"] = 1
    prefs.delete_item("sizes")
    assert server.calls[-1] == ("put", f"preferences/{KEY}", None, {
        "visible": True, "other": 1
    })
    assert prefs.get_data() == {"visible": True, "other": 1}

    prefs.clear()
    assert (KEY, None) not in server.preferences
    assert prefs.get_data() == {}
    # Deleting what does not exist is fine
    prefs.clear()


@pytest.mark.unit
def test_server_support_is_asked_once(monkeypatch):
    server = use_server(monkeypatch, FakeServer())

    assert UserPreferences.is_supported() is True
    assert UserPreferences.is_supported() is True
    assert len(server.calls) == 1
    method, endpoint, _, _ = server.calls[0]
    assert (method, endpoint) == ("get", "preferences")

    # Cached by server
    monkeypatch.setattr(ayon_api, "get_base_url", lambda: "http://other")
    server.status_code = 404
    assert UserPreferences.is_supported() is False
    assert UserPreferences.is_supported() is False
    assert len(server.calls) == 2


@pytest.mark.unit
def test_server_support_asked_by_threads_at_once(monkeypatch):
    server = FakeServer()
    raw_get = server.raw_get

    def slow_raw_get(endpoint, **kwargs):
        time.sleep(0.05)
        return raw_get(endpoint, **kwargs)

    monkeypatch.setattr(ayon_api, "raw_get", slow_raw_get)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(UserPreferences.is_supported())
        )
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [True] * 4
    assert len(server.calls) == 1


@pytest.mark.unit
def test_user_preferences_on_server_without_api(monkeypatch, local_dir):
    server = use_server(monkeypatch, FakeServer(status_code=404))
    prefs = UserPreferences(KEY)

    with pytest.raises(UserPreferencesNotSupported, match="1.17.3"):
        prefs.get_item("visible", default=False)
    # The first request found out the server has no API
    assert UserPreferences.is_supported() is False
    assert len(server.calls) == 1

    for method, args in (
        (prefs.get_data, ()),
        (prefs.refresh, ()),
        (prefs.set_item, ("visible", True)),
        (prefs.delete_item, ("visible",)),
        (prefs.clear, ()),
        (UserPreferences(KEY, project_name="demo").get_data, ()),
    ):
        with pytest.raises(UserPreferencesNotSupported):
            method(*args)
    assert len(server.calls) == 1
    # Nothing is stored on this machine instead
    assert not os.path.exists(os.path.join(local_dir, "tools"))


@pytest.mark.unit
def test_user_preferences_while_server_is_not_reachable(
    monkeypatch, local_dir
):
    server = use_server(monkeypatch, FakeServer(status_code=500))

    prefs = UserPreferences(KEY)
    assert prefs.get_item("visible", default=False) is False
    assert prefs.refresh() is False
    # Not known, so asked again
    calls = len(server.calls)
    assert UserPreferences.is_supported() is False
    assert len(server.calls) == calls + 1

    # Kept for the session, but not written on this machine
    prefs.set_item("visible", True)
    assert prefs.get_item("visible") is True
    assert not os.path.exists(os.path.join(local_dir, "tools"))

    # The server is back
    server.status_code = None
    prefs.set_item("sizes", [1])
    assert server.preferences[(KEY, None)] == {"sizes": [1]}
    assert UserPreferences.is_supported() is True
