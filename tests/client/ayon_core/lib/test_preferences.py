"""Tests for 'LocalPreferences' and 'UserPreferences'."""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import ayon_api
import pytest

import ayon_core
from ayon_core.lib import (
    JSONSettingRegistry,
    LocalPreferences,
    UserPreferences,
    UserPreferencesNotSupported,
    get_launcher_local_dir,
)
from ayon_core.lib import local_settings
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
    monkeypatch.setattr(local_settings._ServerSupport, "by_url", {})
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

    assert prefs.filepath == os.path.join(
        local_dir, "tools", "preferences.db"
    )
    assert prefs.get_item("sizes", default=[]) == []
    with pytest.raises(RegistryItemNotFound):
        prefs.get_item("sizes")
    # Nothing is written until an item is set
    assert not os.path.exists(prefs.filepath)

    prefs.set_item("sizes", [200, 400])
    prefs.set_item("visible", True)
    assert LocalPreferences(KEY).get_item("sizes") == [200, 400]
    assert prefs.get_data() == {"sizes": [200, 400], "visible": True}
    # Other preferences are in the same database
    LocalPreferences(f"{KEY}.other").set_item("sizes", [1, 2])
    assert prefs.get_item("sizes") == [200, 400]

    prefs.delete_item("sizes")
    prefs.delete_item("missing")
    with pytest.raises(RegistryItemNotFound):
        prefs.delete_item("missing", ignore_missing=False)
    assert LocalPreferences(KEY).get_data() == {"visible": True}

    prefs.clear()
    assert prefs.get_data() == {}
    assert LocalPreferences(f"{KEY}.other").get_data() == {"sizes": [1, 2]}


@pytest.mark.unit
def test_local_preferences_import_existing_registry():
    """Registries of tools are imported once, on first use."""
    registry = JSONSettingRegistry("launcher", get_launcher_local_dir("tools"))
    registry.set_item("grouped_hosts", '["maya"]')

    prefs = LocalPreferences("launcher")
    assert prefs.legacy_registry_filepath == registry.filepath
    assert prefs.get_item("grouped_hosts") == '["maya"]'

    prefs.set_item("grouped_hosts", '["maya", "nuke"]')
    prefs.delete_item("grouped_hosts")
    # Not imported again, by this process or another one
    assert LocalPreferences("launcher").get_data() == {}
    assert prefs.import_registry(registry.filepath) is False
    # The registry is left as it was, for older versions of core
    assert registry.get_item("grouped_hosts") == '["maya"]'


@pytest.mark.unit
def test_local_preferences_import_keeps_items_that_are_set(local_dir):
    registry = JSONSettingRegistry("unreal", local_dir)
    registry.set_item("width", 800)
    registry.set_item("height", 600)

    prefs = LocalPreferences("unreal")
    prefs.set_item("width", 1000)
    assert prefs.import_registry(registry.filepath) is True
    assert prefs.get_data() == {"width": 1000, "height": 600}
    assert prefs.import_registry(os.path.join(local_dir, "x.json")) is False


@pytest.mark.unit
def test_local_preferences_import_passed_legacy_registry(local_dir):
    registry = JSONSettingRegistry("unreal", local_dir)
    registry.set_item("width", 800)

    prefs = LocalPreferences(
        "unreal", legacy_registry_filepath=registry.filepath
    )
    assert prefs.legacy_registry_filepath == registry.filepath
    assert prefs.get_item("width") == 800
    # The default legacy registry is not imported instead
    assert LocalPreferences("unreal").legacy_registry_filepath == (
        os.path.join(local_dir, "tools", "unreal.json")
    )


@pytest.mark.unit
def test_json_registry_reads_changes_of_others():
    path = get_launcher_local_dir("tools")
    registry = JSONSettingRegistry("other_tool", path)
    # Unhashable default, the registry used to cache with 'lru_cache'
    assert registry.get_item("tabs", default=[]) == []
    assert registry.get_item("width", default=None) is None

    JSONSettingRegistry("other_tool", path).set_item("width", 800)
    assert registry.get_item("width", default=None) == 800


@pytest.mark.unit
@pytest.mark.parametrize(
    "content",
    [
        '{"registry": {"width": 800},',
        '["width"]',
        '{"registry": ["width"]}',
    ],
    ids=["broken", "not_a_dict", "registry_not_a_dict"],
)
def test_json_registry_keeps_a_file_it_cannot_parse(content, local_dir):
    """Items of a file that can't be read are not overwritten."""
    registry = JSONSettingRegistry("other_tool", local_dir)
    with open(registry.filepath, "w") as stream:
        stream.write(content)

    assert registry.get_item("width", default=None) is None
    registry.set_item("height", 600)
    registry.delete_item("width")
    with open(registry.filepath, "r") as stream:
        assert stream.read() == content


@pytest.mark.unit
def test_json_registry_keeps_a_file_it_cannot_open(local_dir, monkeypatch):
    registry = JSONSettingRegistry("other_tool", local_dir)
    registry.set_item("width", 800)

    def open_file(*args, **kwargs):
        raise PermissionError("Used by another process")

    with monkeypatch.context() as context:
        context.setattr(local_settings, "open", open_file, raising=False)
        assert registry.get_item("width", default=None) is None
        registry.set_item("height", 600)
        registry.delete_item("width")
    assert registry.get_data() == {"width": 800}


def broken_databases(prefs: LocalPreferences) -> list[str]:
    dirpath = os.path.dirname(prefs.filepath)
    return sorted(
        filename
        for filename in os.listdir(dirpath)
        if filename.startswith("preferences.db.broken-")
    )


def fill_database(prefs: LocalPreferences) -> None:
    """Items for pages after the first one, in one transaction."""
    prefs.set_item("first", True)
    connection = sqlite3.connect(prefs.filepath)
    with connection:
        connection.executemany(
            "INSERT INTO preferences (name, item, value) VALUES (?, ?, ?)",
            [(KEY, f"item_{index}", '"' + "x" * 200 + '"')
             for index in range(200)],
        )
    connection.close()


def damage_database(prefs: LocalPreferences) -> None:
    """Overwrite pages after the header, SQLite reports it malformed."""
    with open(prefs.filepath, "rb") as stream:
        content = bytearray(stream.read())
    content[4096:] = b"\xab" * (len(content) - 4096)
    with open(prefs.filepath, "wb") as stream:
        stream.write(content)


@pytest.mark.unit
def test_local_preferences_replace_a_file_that_is_not_a_database():
    prefs = LocalPreferences(KEY)
    os.makedirs(os.path.dirname(prefs.filepath))
    with open(prefs.filepath, "w") as stream:
        stream.write("not a database" * 100)

    assert prefs.get_item("visible", default=False) is False
    assert len(broken_databases(prefs)) == 1
    prefs.set_item("visible", True)
    assert LocalPreferences(KEY).get_item("visible") is True


@pytest.mark.unit
def test_local_preferences_replace_a_malformed_database():
    prefs = LocalPreferences(KEY)
    fill_database(prefs)
    damage_database(prefs)

    prefs.set_item("visible", True)
    assert prefs.get_data() == {"visible": True}
    assert len(broken_databases(prefs)) == 1


@pytest.mark.unit
def test_local_preferences_keep_a_locked_database(monkeypatch):
    prefs = LocalPreferences(KEY)
    prefs.set_item("visible", True)
    monkeypatch.setattr(LocalPreferences, "timeout", 0.1)

    other = sqlite3.connect(prefs.filepath, isolation_level=None)
    try:
        other.execute("BEGIN EXCLUSIVE")
        # Failed, logged and not raised
        prefs.set_item("visible", False)
        assert prefs.get_item("visible", default=None) is None
    finally:
        other.close()

    assert broken_databases(prefs) == []
    assert prefs.get_item("visible") is True


@pytest.mark.unit
def test_local_preferences_broken_database_that_cannot_be_moved(
    monkeypatch,
):
    prefs = LocalPreferences(KEY)
    fill_database(prefs)
    damage_database(prefs)

    def replace(src, dst):
        raise PermissionError("Used by another process")

    with monkeypatch.context() as context:
        context.setattr(os, "replace", replace)
        assert prefs.get_item("visible", default=False) is False
        prefs.set_item("visible", True)
    assert broken_databases(prefs) == []

    # Moved on the next access that can move it
    prefs.set_item("visible", True)
    assert prefs.get_data() == {"visible": True}
    assert len(broken_databases(prefs)) == 1


@pytest.mark.unit
def test_local_preferences_values_that_are_not_json():
    prefs = LocalPreferences(KEY)
    prefs.set_item("visible", True)
    prefs.set_item("visible", {1, 2})
    assert prefs.get_item("visible") is True


@pytest.mark.unit
def test_local_preferences_changed_by_processes_at_once(local_dir):
    """Items changed by processes at the same time are all kept."""
    client_dir = os.path.dirname(os.path.dirname(ayon_core.__file__))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (client_dir, env.get("PYTHONPATH")) if path
    )
    script = (
        "import sys\n"
        "from ayon_core.lib import LocalPreferences\n"
        f"prefs = LocalPreferences({KEY!r})\n"
        "for index in range(20):\n"
        "    prefs.set_item(f'{sys.argv[1]}_{index}', index)\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, f"process{number}"], env=env
        )
        for number in range(4)
    ]
    for process in processes:
        assert process.wait(timeout=60) == 0

    assert LocalPreferences(KEY).get_data() == {
        f"process{number}_{index}": index
        for number in range(4)
        for index in range(20)
    }


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
