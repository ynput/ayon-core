"""Test task in-use tracking in the pipeline module."""
from __future__ import annotations

import datetime
import threading
from dataclasses import replace
from typing import Any, Optional

import pytest

from ayon_core.pipeline.workfile import task_usage
from ayon_core.pipeline.workfile.task_usage import (
    TaskUsageItem,
    TaskUsageNotSupportedError,
    TaskUsageSettings,
    TaskUsageTracker,
    filter_other_users_items,
    get_same_workfile_items,
    get_task_usage_settings,
    is_task_usage_enabled_in_project,
)

NOW = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
ENDPOINT = (
    f"addons/core/{task_usage.__version__}/projects/project/taskInUse"
)


def _item(
    session_id: str = "session-1",
    username: str = "artist1",
    site_id: str = "site-1",
    host_name: Optional[str] = "maya",
    hours_ago: float = 0.0,
    opened_hours_ago: Optional[float] = None,
) -> TaskUsageItem:
    if opened_hours_ago is None:
        opened_hours_ago = hours_ago
    updated_at = NOW - datetime.timedelta(hours=hours_ago)
    opened_at = NOW - datetime.timedelta(hours=opened_hours_ago)
    return TaskUsageItem(
        session_id=session_id,
        username=username,
        machine="machine",
        site_id=site_id,
        host_name=host_name,
        workfile="sh010_anim_v001.ma",
        opened_at=opened_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


def _server_data(item: TaskUsageItem) -> dict[str, Any]:
    """Session data as are returned by the server."""
    return {
        "sessionId": item.session_id,
        "username": item.username,
        "machine": item.machine,
        "siteId": item.site_id,
        "hostName": item.host_name,
        "workfile": item.workfile,
        "openedAt": item.opened_at,
        "updatedAt": item.updated_at,
    }


def test_item_data_roundtrip():
    item = _item()
    assert TaskUsageItem.from_data(item.to_data()) == item
    assert TaskUsageItem.from_server_data(_server_data(item)) == item


def test_item_to_server_data():
    """Username and times are filled by the server."""
    assert _item().to_server_data() == {
        "machine": "machine",
        "siteId": "site-1",
        "hostName": "maya",
        "workfile": "sh010_anim_v001.ma",
    }


@pytest.mark.parametrize(
    "data",
    [
        None,
        "invalid",
        {},
        {"session_id": "a", "username": "b"},
        {"session_id": "a", "username": "b", "updated_at": "invalid"},
        {"session_id": "", "username": "b", "updated_at": NOW.isoformat()},
    ]
)
def test_item_from_invalid_data(data):
    assert TaskUsageItem.from_data(data) is None


@pytest.mark.parametrize(
    "data",
    [
        None,
        "invalid",
        {},
        {"sessionId": "a", "username": "b"},
        {"sessionId": "a", "username": "b", "updatedAt": "invalid"},
        {"sessionId": "", "username": "b", "updatedAt": NOW.isoformat()},
    ]
)
def test_item_from_invalid_server_data(data):
    assert TaskUsageItem.from_server_data(data) is None


def test_filter_other_users_items():
    mine = _item("mine-other-host", host_name="nuke")
    other = _item("other", username="artist2")
    assert filter_other_users_items([mine, other], "artist1") == [other]
    # User was already notified about the session
    assert filter_other_users_items(
        [mine, other], "artist1", {"other"}
    ) == []


def test_user_full_names(monkeypatch):
    items = [
        _item("a", username="artist1"),
        _item("b", username="artist2"),
        _item("c", username="restricted"),
    ]
    monkeypatch.setattr(
        task_usage.ayon_api,
        "get_users",
        lambda **kwargs: iter([
            {"name": "artist1", "attrib": {"fullName": "Artist One"}},
            {"name": "artist2", "attrib": {"fullName": None}},
        ]),
    )
    assert task_usage.get_task_usage_user_full_names(items) == {
        "artist1": "Artist One"
    }

    def _failing(**kwargs):
        raise RuntimeError("Not allowed")

    monkeypatch.setattr(task_usage.ayon_api, "get_users", _failing)
    assert task_usage.get_task_usage_user_full_names(items) == {}


def _settings(profiles: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    workfiles = {}
    if profiles is not None:
        workfiles["task_in_use_profiles"] = profiles
    return {"core": {"tools": {"Workfiles": workfiles}}}


def _profile(**kwargs: Any) -> dict[str, Any]:
    profile = {
        "host_names": [],
        "task_types": [],
        "task_names": [],
        "enabled": True,
        "session_timeout_minutes": 2.0,
    }
    profile.update(kwargs)
    return profile


def test_settings_disabled_by_default():
    for profiles in (None, []):
        project_settings = _settings(profiles)
        settings = get_task_usage_settings(
            "project", "maya", "Animation", "anim", project_settings
        )
        assert settings == TaskUsageSettings(enabled=False)
        assert not is_task_usage_enabled_in_project(
            "project", project_settings
        )


def test_settings_profile_filtering():
    project_settings = _settings([_profile(host_names=["maya"])])
    assert is_task_usage_enabled_in_project("project", project_settings)
    settings = get_task_usage_settings(
        "project", "maya", "Animation", "anim", project_settings
    )
    assert settings == TaskUsageSettings(True, 2.0)

    settings = get_task_usage_settings(
        "project", "nuke", "Compositing", "comp", project_settings
    )
    assert settings.enabled is False

    assert not is_task_usage_enabled_in_project(
        "project", _settings([_profile(enabled=False)])
    )


def test_settings_without_timeout():
    """Profile created before the timeout was added to settings."""
    profile = _profile()
    profile.pop("session_timeout_minutes")
    settings = get_task_usage_settings(
        "project", "maya", "Animation", "anim", _settings([profile])
    )
    assert settings == TaskUsageSettings(True)


@pytest.mark.parametrize(
    "minutes, ttl",
    [
        (5.0, 300),
        (2.5, 150),
        # Limits of the server
        (0.1, task_usage.MIN_TTL_SECONDS),
        (600.0, task_usage.MAX_TTL_SECONDS),
    ]
)
def test_settings_ttl_and_heartbeat_interval(minutes, ttl):
    settings = TaskUsageSettings(True, minutes)
    assert settings.ttl_seconds == ttl
    # Session must survive missed heartbeats
    assert settings.heartbeat_interval * 3 <= settings.ttl_seconds
    assert settings.heartbeat_interval >= 20


class _Response:
    def __init__(self, status_code: int = 200, data: Any = None):
        self.status_code = status_code
        self.data = data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"Request failed: {self.status_code}")


class _MockServer:
    """Mocked task in-use endpoints of the core addon.

    Sessions are stored as server data by task id and session id. Username
    and times are filled by the server.
    """
    def __init__(self):
        self.sessions: dict[str, dict[str, dict[str, Any]]] = {}
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.status_code = 200
        self.username = "artist1"
        self.now = NOW

    def add(self, task_id: str, *items: TaskUsageItem) -> None:
        for item in items:
            self.sessions.setdefault(task_id, {})[item.session_id] = (
                _server_data(item)
            )

    def _task_sessions(self, task_id: str) -> list[dict[str, Any]]:
        return list(self.sessions.get(task_id, {}).values())

    def _subpaths(self, method, endpoint, kwargs) -> list[str]:
        self.requests.append((method, endpoint, kwargs))
        assert endpoint.startswith(f"{ENDPOINT}/")
        return endpoint[len(ENDPOINT) + 1:].split("/")

    def get(self, endpoint, **kwargs):
        (task_id,) = self._subpaths("get", endpoint, kwargs)
        if self.status_code != 200:
            return _Response(self.status_code)
        return _Response(data={"sessions": self._task_sessions(task_id)})

    def post(self, endpoint, **kwargs):
        (subpath,) = self._subpaths("post", endpoint, kwargs)
        assert subpath == "query"
        if self.status_code != 200:
            return _Response(self.status_code)
        return _Response(data={"tasks": {
            task_id: self._task_sessions(task_id)
            for task_id in kwargs["taskIds"]
            if self._task_sessions(task_id)
        }})

    def put(self, endpoint, **kwargs):
        task_id, session_id = self._subpaths("put", endpoint, kwargs)
        if self.status_code != 200:
            return _Response(self.status_code)
        sessions = self.sessions.setdefault(task_id, {})
        existing = sessions.get(session_id)
        now = self.now.isoformat()
        opened_at = updated_at = now
        if existing:
            opened_at = existing["openedAt"]
            if kwargs["heartbeat"]:
                updated_at = existing["updatedAt"]
        sessions[session_id] = {
            "sessionId": session_id,
            "username": self.username,
            "machine": kwargs["machine"],
            "siteId": kwargs["siteId"],
            "hostName": kwargs["hostName"],
            "workfile": kwargs["workfile"],
            "openedAt": opened_at,
            "updatedAt": updated_at,
        }
        return _Response(data={
            "sessions": self._task_sessions(task_id),
            "ttl": kwargs["ttl"],
        })

    def delete(self, endpoint, **kwargs):
        task_id, session_id = self._subpaths("delete", endpoint, kwargs)
        if self.status_code != 200:
            return _Response(self.status_code)
        self.sessions.get(task_id, {}).pop(session_id, None)
        return _Response(204)


@pytest.fixture
def server(monkeypatch):
    """Mocked server calls."""
    mock_server = _MockServer()

    monkeypatch.setattr(task_usage, "_endpoints_supported", None)
    monkeypatch.setattr(task_usage, "_get_now", lambda: NOW)
    monkeypatch.setattr(task_usage, "_get_session_id", lambda: "mine")
    monkeypatch.setattr(task_usage, "get_ayon_username", lambda: "artist1")
    monkeypatch.setattr(task_usage, "get_local_site_id", lambda: "site-1")
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(
        task_usage.ayon_api,
        "get_addon_endpoint",
        lambda name, version, *subpaths: "/".join(
            ("addons", name, version) + subpaths
        ),
    )

    def _raw_request(method):
        def _request(endpoint, json=None, timeout=None):
            # Callbacks of the application must not wait for long
            assert timeout == task_usage.REQUEST_TIMEOUT_SECONDS
            return getattr(mock_server, method)(endpoint, **(json or {}))
        return _request

    for method in ("get", "post", "put", "delete"):
        monkeypatch.setattr(
            task_usage.ayon_api, f"raw_{method}", _raw_request(method)
        )
    return mock_server


def test_claim_update_and_release(server):
    other = _item("other", username="artist3")
    server.add("task-id", other)

    item = task_usage.create_session_item("file.ma", "maya")
    assert task_usage.claim_task("project", "task-id", item, 120) == [other]
    assert server.requests == [(
        "put",
        f"{ENDPOINT}/task-id/mine",
        {
            "ttl": 120,
            "heartbeat": False,
            "machine": item.machine,
            "siteId": "site-1",
            "hostName": "maya",
            "workfile": "file.ma",
        },
    )]
    assert set(server.sessions["task-id"]) == {"other", "mine"}

    server.now = NOW + datetime.timedelta(hours=1)
    task_usage.update_task_session(
        "project", "task-id", item, 120, heartbeat=True
    )
    assert server.requests[-1][2]["heartbeat"] is True
    session = server.sessions["task-id"]["mine"]
    assert session["openedAt"] == session["updatedAt"] == NOW.isoformat()

    task_usage.update_task_session("project", "task-id", item)
    assert server.requests[-1][2]["ttl"] == TaskUsageSettings().ttl_seconds
    session = server.sessions["task-id"]["mine"]
    assert session["openedAt"] == NOW.isoformat()
    assert session["updatedAt"] == server.now.isoformat()

    task_usage.release_task("project", "task-id")
    assert server.requests[-1][:2] == (
        "delete", f"{ENDPOINT}/task-id/mine"
    )
    assert set(server.sessions["task-id"]) == {"other"}


def test_get_task_usage_items(server):
    mine = _item("mine")
    other = _item("other", username="artist2")
    server.add("task-id", mine, other)
    server.sessions["task-id"]["invalid"] = {"sessionId": "invalid"}

    assert task_usage.get_task_usage_items("project", "task-id") == [
        mine, other
    ]
    assert task_usage.get_task_usage_items("project", "unused") == []


def test_get_tasks_usage_items(server):
    mine = _item("mine")
    other = _item("other", username="artist2")
    server.add("task-1", mine)
    server.add("task-2", other)
    server.add("task-3", other)

    assert task_usage.get_tasks_usage_items(
        "project", ["task-1", "task-2", "unused"]
    ) == {
        "task-1": [mine],
        "task-2": [other],
        "unused": [],
    }
    # Server is not asked without tasks
    requests_count = len(server.requests)
    assert task_usage.get_tasks_usage_items("project", []) == {}
    assert len(server.requests) == requests_count


def test_other_users_task_usage_items(server):
    mine = _item("mine")
    other = _item("other", username="artist2")
    server.add("task-id", mine, other)

    assert task_usage.get_other_users_task_usage_items(
        "project", "task-id"
    ) == [other]

    task_usage.acknowledge_task_usage_items([other])
    assert task_usage.get_other_users_task_usage_items(
        "project", "task-id"
    ) == []


def test_server_without_endpoints(server):
    """Older server addon does not have the endpoints."""
    server.status_code = 404
    item = _item("mine")

    assert task_usage.is_task_usage_supported()
    assert task_usage.get_task_usage_items("project", "task-id") == []
    assert not task_usage.is_task_usage_supported()
    assert len(server.requests) == 1

    # Server is not asked again
    assert task_usage.get_other_users_task_usage_items(
        "project", "task-id"
    ) == []
    assert task_usage.get_tasks_usage_items("project", ["task-id"]) == {
        "task-id": []
    }
    task_usage.release_task("project", "task-id")
    with pytest.raises(TaskUsageNotSupportedError):
        task_usage.claim_task("project", "task-id", item)
    with pytest.raises(TaskUsageNotSupportedError):
        task_usage.update_task_session("project", "task-id", item)
    assert len(server.requests) == 1


def test_server_error_is_raised(server):
    """Failed request is not considered as missing endpoints."""
    server.status_code = 500
    with pytest.raises(RuntimeError):
        task_usage.get_task_usage_items("project", "task-id")
    assert task_usage.is_task_usage_supported()


class _MockHost:
    name = "maya"

    def __init__(self):
        self.task_name = "anim"
        self.workfile = "/path/sh010_anim_v001.ma"

    def get_current_context(self):
        return {
            "project_name": "project",
            "folder_path": "/shots/sh010",
            "task_name": self.task_name,
        }

    def get_current_workfile(self):
        return self.workfile


def _mock_task_context(tracker, monkeypatch):
    """Task id is the same as task name.

    Task 'disabled' does not have enabled in-use tracking.
    """
    def _query_task_context(project_name, folder_path, task_name):
        if task_name == "disabled":
            return None
        return task_usage._TaskContext(
            project_name, task_name, TaskUsageSettings(True)
        )

    monkeypatch.setattr(tracker, "_query_task_context", _query_task_context)


def _sync(tracker: TaskUsageTracker) -> None:
    """Schedule current context and process it as the thread would do."""
    tracker.sync()
    tracker.process()


@pytest.fixture
def tracker_calls(server, monkeypatch):
    """Tracker with mocked server calls.

    Task id is the same as task name, task 'disabled' does not have enabled
    in-use tracking. Task 'in-use' is in use by other user, who has opened
    workfile 'sh010_anim_v001.ma'.
    """
    calls = []
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    other_user = _item("other-user", username="artist2")
    notices = []

    def _claim_task(project_name, task_id, item, ttl):
        calls.append(("claim", task_id, item.workfile))
        if task_id == "in-use":
            return [other_user]
        return []

    def _update_task_session(
        project_name, task_id, item, ttl, heartbeat=False
    ):
        name = "heartbeat" if heartbeat else "update"
        calls.append((name, task_id, item.workfile))

    def _release_task(project_name, task_id, session_id):
        calls.append(("release", task_id, session_id))

    _mock_task_context(tracker, monkeypatch)
    monkeypatch.setattr(task_usage, "_notice_callbacks", [notices.append])
    monkeypatch.setattr(
        task_usage,
        "get_task_usage_user_full_names",
        lambda items: {"artist2": "Artist Two"},
    )
    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    monkeypatch.setattr(
        task_usage, "update_task_session", _update_task_session
    )
    monkeypatch.setattr(task_usage, "release_task", _release_task)
    return host, tracker, calls, notices


@pytest.fixture
def current_time(monkeypatch):
    value = [1000.0]
    monkeypatch.setattr(task_usage.time, "monotonic", lambda: value[0])
    return value


def test_tracker_sync_does_not_use_server(tracker_calls, monkeypatch):
    """Callbacks of the application do not wait for the server."""
    host, tracker, calls, _ = tracker_calls

    def _failing(*args, **kwargs):
        raise AssertionError("Server must not be used in 'sync'")

    monkeypatch.setattr(tracker, "_query_task_context", _failing)
    monkeypatch.setattr(tracker, "process", _failing)
    for name in ("raw_get", "raw_post", "raw_put", "raw_delete"):
        monkeypatch.setattr(task_usage.ayon_api, name, _failing)

    tracker.sync()
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()
    tracker.release()
    assert calls == []


def test_tracker_claims_and_releases(tracker_calls, current_time):
    host, tracker, calls, _ = tracker_calls

    _sync(tracker)
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Nothing did change
    _sync(tracker)
    tracker.process()
    assert len(calls) == 1

    # Workfile did change, session is only updated
    host.workfile = "/path/sh010_anim_v002.ma"
    _sync(tracker)
    assert calls[1:] == [("update", "anim", "sh010_anim_v002.ma")]

    # Task did change
    host.task_name = "layout"
    _sync(tracker)
    assert calls[2:] == [
        ("release", "anim", "mine"),
        ("claim", "layout", "sh010_anim_v002.ma"),
    ]

    # Task without enabled tracking
    host.task_name = "disabled"
    _sync(tracker)
    assert calls[4:] == [("release", "layout", "mine")]

    # Nothing is claimed
    tracker.release()
    tracker.process()
    assert len(calls) == 5


def test_tracker_processes_only_last_context(tracker_calls):
    """Only the last context is processed if the server is slow."""
    host, tracker, calls, _ = tracker_calls

    tracker.sync()
    host.task_name = "layout"
    tracker.sync()
    host.workfile = "/path/sh010_layout_v001.ma"
    tracker.sync()
    tracker.process()
    assert calls == [("claim", "layout", "sh010_layout_v001.ma")]


def test_tracker_release_and_claim_again(tracker_calls):
    host, tracker, calls, _ = tracker_calls

    _sync(tracker)
    tracker.release()
    tracker.process()
    assert calls[1:] == [("release", "anim", "mine")]

    _sync(tracker)
    assert calls[2:] == [("claim", "anim", "sh010_anim_v001.ma")]


def test_tracker_uses_server_times(server, monkeypatch):
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    monkeypatch.setattr(
        tracker,
        "_query_task_context",
        lambda *args: task_usage._TaskContext(
            "project", "task-id", TaskUsageSettings(True, 2.0)
        ),
    )
    _sync(tracker)

    server.now = later = NOW + datetime.timedelta(hours=1)
    host.workfile = "/path/sh010_anim_v002.ma"
    _sync(tracker)

    session = server.sessions["task-id"]["mine"]
    assert session["openedAt"] == NOW.isoformat()
    assert session["updatedAt"] == later.isoformat()
    assert session["workfile"] == "sh010_anim_v002.ma"
    assert [
        (method, kwargs["ttl"], kwargs["heartbeat"])
        for method, _, kwargs in server.requests
    ] == [("put", 120, False), ("put", 120, False)]

    tracker.stop()
    assert server.sessions["task-id"] == {}


def test_tracker_notifies_about_other_users(tracker_calls):
    host, tracker, calls, notices = tracker_calls

    host.task_name = "in-use"
    host.workfile = "/path/sh010_anim_v002.ma"
    _sync(tracker)
    assert calls == [("claim", "in-use", "sh010_anim_v002.ma")]
    (notice,) = notices
    assert [item.session_id for item in notice.items] == ["other-user"]
    assert notice.user_full_names == {"artist2": "Artist Two"}
    assert notice.workfile == "sh010_anim_v002.ma"
    # Other user has opened different workfile
    assert notice.version_up_callback is None
    # Sessions are acknowledged by the frontend that did show the notice
    assert task_usage._acknowledged_session_ids == set()


def test_tracker_notice_offers_version_up(tracker_calls, monkeypatch):
    """Version up is offered if other user has opened the same workfile."""
    host, tracker, calls, notices = tracker_calls
    version_ups = []
    monkeypatch.setattr(tracker, "_version_up", version_ups.append)

    host.task_name = "in-use"
    _sync(tracker)
    (notice,) = notices
    notice.version_up_callback()
    assert version_ups == ["sh010_anim_v001.ma"]


def test_tracker_notice_without_frontend(tracker_calls, monkeypatch):
    """User is asked in the Workfiles tool if nothing shows the notice."""
    host, tracker, calls, notices = tracker_calls

    def _failing(notice):
        raise RuntimeError("Frontend is broken")

    for callbacks in ([], [_failing]):
        monkeypatch.setattr(task_usage, "_notice_callbacks", callbacks)
        host.task_name = "in-use"
        _sync(tracker)
        assert calls[-1] == ("claim", "in-use", "sh010_anim_v001.ma")
        assert task_usage._acknowledged_session_ids == set()
        assert not tracker._failed
        host.task_name = "disabled"
        _sync(tracker)


def test_notice_callbacks_registration(monkeypatch):
    monkeypatch.setattr(task_usage, "_notice_callbacks", [])
    notices = []

    task_usage.register_task_in_use_notice_callback(notices.append)
    task_usage.register_task_in_use_notice_callback(notices.append)
    assert len(task_usage._notice_callbacks) == 1

    task_usage.deregister_task_in_use_notice_callback(notices.append)
    task_usage.deregister_task_in_use_notice_callback(notices.append)
    assert task_usage._notice_callbacks == []


def test_tracker_skips_acknowledged_users(tracker_calls):
    """Sessions confirmed before are not notified again."""
    host, tracker, calls, notices = tracker_calls

    task_usage.acknowledge_task_usage_items(
        [_item("other-user", username="artist2")]
    )
    host.task_name = "in-use"
    _sync(tracker)
    assert calls == [("claim", "in-use", "sh010_anim_v001.ma")]
    assert notices == []


def test_tracker_reports_activity(tracker_calls, current_time):
    """Saved workfile is activity, but each save is not reported."""
    host, tracker, calls, _ = tracker_calls

    _sync(tracker)
    current_time[0] += task_usage.ACTIVITY_INTERVAL_SECONDS - 1
    _sync(tracker)
    assert len(calls) == 1

    current_time[0] += 2
    # Nothing happened in the application
    tracker.process()
    assert len(calls) == 1

    _sync(tracker)
    assert calls[1:] == [("update", "anim", "sh010_anim_v001.ma")]


def test_tracker_heartbeat(tracker_calls, current_time):
    host, tracker, calls, _ = tracker_calls
    interval = TaskUsageSettings(True).heartbeat_interval

    # Nothing is claimed
    tracker.process()
    assert calls == []
    assert tracker._get_wait_seconds() == interval

    _sync(tracker)
    # Session was updated a moment ago
    current_time[0] += interval / 2
    tracker.process()
    assert len(calls) == 1
    assert tracker._get_wait_seconds() == interval / 2

    current_time[0] += interval / 2
    tracker.process()
    assert calls[1:] == [("heartbeat", "anim", "sh010_anim_v001.ma")]
    assert tracker._get_wait_seconds() == interval

    tracker.release()
    tracker.process()
    current_time[0] += interval
    tracker.process()
    assert calls[2:] == [("release", "anim", "mine")]


def test_tracker_does_not_raise(tracker_calls, current_time, monkeypatch):
    host, tracker, calls, _ = tracker_calls
    interval = TaskUsageSettings(True).heartbeat_interval
    failed_calls = []

    def _failing(*args, **kwargs):
        failed_calls.append(1)
        raise RuntimeError("Server is not available")

    # Failed host integration
    get_current_context = host.get_current_context
    host.get_current_context = _failing
    tracker.sync()
    host.get_current_context = get_current_context

    claim_task = task_usage.claim_task
    monkeypatch.setattr(task_usage, "claim_task", _failing)
    _sync(tracker)
    # Claim is repeated, the server may be available again
    tracker.process()
    assert len(failed_calls) == 3
    assert not tracker.is_disabled

    monkeypatch.setattr(task_usage, "claim_task", claim_task)
    tracker.process()
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Failed heartbeat is not repeated immediately
    monkeypatch.setattr(task_usage, "update_task_session", _failing)
    current_time[0] += interval
    tracker.process()
    assert len(failed_calls) == 4
    assert tracker._get_wait_seconds() == interval

    monkeypatch.setattr(task_usage, "release_task", _failing)
    tracker.stop()
    assert len(failed_calls) == 5


def test_tracker_is_disabled_without_endpoints(
    server, current_time, monkeypatch
):
    """Tracker does nothing if the server addon is older."""
    server.status_code = 404
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    _mock_task_context(tracker, monkeypatch)

    _sync(tracker)
    assert tracker.is_disabled
    assert len(server.requests) == 1

    current_time[0] += TaskUsageSettings(True).heartbeat_interval
    host.workfile = "/path/sh010_anim_v002.ma"
    _sync(tracker)
    tracker.release()
    tracker.start()
    assert tracker._thread is None
    tracker.stop()
    assert len(server.requests) == 1


def test_tracker_is_disabled_by_heartbeat(
    server, current_time, monkeypatch
):
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    _mock_task_context(tracker, monkeypatch)

    _sync(tracker)
    assert not tracker.is_disabled

    server.status_code = 404
    current_time[0] += TaskUsageSettings(True).heartbeat_interval
    tracker.process()
    assert tracker.is_disabled


def test_tracker_thread(tracker_calls, monkeypatch):
    """Scheduled context is processed and released by the thread."""
    host, tracker, calls, _ = tracker_calls
    main_thread = threading.current_thread()
    threads = []
    claimed = threading.Event()
    claim_task = task_usage.claim_task

    def _claim_task(*args):
        threads.append(threading.current_thread())
        output = claim_task(*args)
        claimed.set()
        return output

    def _release_task(*args):
        threads.append(threading.current_thread())
        calls.append(("release", args[1], args[2]))

    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    monkeypatch.setattr(task_usage, "release_task", _release_task)

    tracker.start()
    thread = tracker._thread
    assert thread is not None and thread.daemon
    # Thread is started only once
    tracker.start()
    assert tracker._thread is thread

    tracker.sync()
    assert claimed.wait(5)

    tracker.stop(timeout=5)
    assert not thread.is_alive()
    assert tracker._thread is None
    assert calls == [
        ("claim", "anim", "sh010_anim_v001.ma"),
        ("release", "anim", "mine"),
    ]
    assert threads == [thread, thread]
    assert main_thread not in threads


def test_tracker_stop_does_not_wait_for_server(tracker_calls, monkeypatch):
    """Exit of the application is not blocked by slow server."""
    host, tracker, calls, _ = tracker_calls
    release_started = threading.Event()
    finish_release = threading.Event()

    def _release_task(*args):
        release_started.set()
        finish_release.wait(5)

    monkeypatch.setattr(task_usage, "release_task", _release_task)
    _sync(tracker)
    tracker.start()
    thread = tracker._thread
    tracker.stop(timeout=0.05)
    # Thread is still releasing the task
    assert release_started.wait(5)
    assert thread.is_alive()

    # Nothing happens in current thread when exit is called again
    tracker.stop(timeout=0.05)

    finish_release.set()
    thread.join(5)
    assert not thread.is_alive()


def test_tracker_stop_without_thread(tracker_calls):
    host, tracker, calls, _ = tracker_calls

    _sync(tracker)
    tracker.stop()
    assert calls[1:] == [("release", "anim", "mine")]
    tracker.stop()
    assert len(calls) == 2


def test_tracker_processes_if_thread_is_starved(
    tracker_calls, current_time, monkeypatch
):
    """Context is processed in 'sync' if the thread does not run."""
    host, tracker, calls, _ = tracker_calls
    # Thread that never runs
    monkeypatch.setattr(tracker, "_thread", object())

    tracker.sync()
    current_time[0] += task_usage.STARVED_THREAD_SECONDS - 1
    tracker.sync()
    assert calls == []

    current_time[0] += 2
    tracker.sync()
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Thread is not starved if it is waiting for the server
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()
    current_time[0] += task_usage.STARVED_THREAD_SECONDS + 1
    with tracker._process_lock:
        tracker.sync()
    assert len(calls) == 1


def test_tracker_skips_queries_if_not_used_in_project(monkeypatch):
    def _failing(*args, **kwargs):
        raise AssertionError("Server should not be asked")

    monkeypatch.setattr(
        task_usage, "get_project_settings", lambda *args: _settings([])
    )
    monkeypatch.setattr(task_usage.ayon_api, "get_folder_by_path", _failing)
    monkeypatch.setattr(task_usage.ayon_api, "raw_put", _failing)

    tracker = TaskUsageTracker(_MockHost())
    tracker.sync()
    tracker._process()
    assert tracker._claimed is None


def _prepare_install(monkeypatch):
    started = []
    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: False)
    monkeypatch.setattr(task_usage, "is_in_tests", lambda: False)
    for key in task_usage.FARM_JOB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(task_usage, "register_event_callback", lambda *a: None)
    monkeypatch.setattr(task_usage.atexit, "register", lambda *a: None)
    monkeypatch.setattr(task_usage, "_connect_qt_quit", lambda: None)
    monkeypatch.setattr(
        task_usage, "_install_notice_frontend", lambda: started.append("ui")
    )
    monkeypatch.setattr(
        TaskUsageTracker, "sync", lambda self: started.append("sync")
    )
    monkeypatch.setattr(
        TaskUsageTracker, "start", lambda self: started.append("start")
    )
    return started


def test_tracker_install_uses_acknowledged_env(monkeypatch):
    started = _prepare_install(monkeypatch)
    monkeypatch.setenv(task_usage.ACKNOWLEDGED_SESSIONS_ENV_KEY, "a,b,")

    assert task_usage.install_task_usage_tracker(_MockHost()) is not None
    assert task_usage._acknowledged_session_ids == {"a", "b"}
    # Frontend is ready before the first notice can be created
    assert started == ["ui", "sync", "start"]


def test_tracker_uninstall(monkeypatch):
    _prepare_install(monkeypatch)
    stopped = []
    monkeypatch.setattr(
        TaskUsageTracker,
        "stop",
        lambda self, timeout=None: stopped.append(timeout),
    )
    task_usage.install_task_usage_tracker(_MockHost())
    task_usage._on_exit()
    task_usage.uninstall_task_usage_tracker()
    task_usage.uninstall_task_usage_tracker()
    task_usage._on_exit()
    assert stopped == [task_usage.EXIT_TIMEOUT_SECONDS] * 2


def test_tracker_install_skipped_in_headless(monkeypatch):
    started = _prepare_install(monkeypatch)
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: True)
    assert task_usage.install_task_usage_tracker(_MockHost()) is None
    assert started == []


def test_tracker_install_skipped_in_tests(monkeypatch):
    started = _prepare_install(monkeypatch)
    monkeypatch.setattr(task_usage, "is_in_tests", lambda: True)
    assert task_usage.install_task_usage_tracker(_MockHost()) is None
    assert started == []


@pytest.mark.parametrize("env_key", task_usage.FARM_JOB_ENV_KEYS)
def test_tracker_install_skipped_in_farm_jobs(monkeypatch, env_key):
    _prepare_install(monkeypatch)
    # Deadline sets all the keys in a job, only one of them to "1"
    for key in task_usage.FARM_JOB_ENV_KEYS:
        monkeypatch.setenv(key, "0")
    assert task_usage.install_task_usage_tracker(_MockHost()) is not None

    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setenv(env_key, "1")
    assert task_usage.install_task_usage_tracker(_MockHost()) is None


def test_same_workfile_items():
    same = _item("same", username="artist2")
    other = replace(_item("other", username="artist3"), workfile="b_v002.ma")
    no_file = replace(_item("none", username="artist4"), workfile=None)
    items = [same, other, no_file]

    assert get_same_workfile_items(items, None) == []
    assert get_same_workfile_items(items, "sh010_anim_v001.ma") == [same]
    # Path can be used and letter case is ignored
    assert get_same_workfile_items(
        items, "/work/SH010_anim_v001.ma"
    ) == [same]
    assert get_same_workfile_items(items, "sh010_anim_v003.ma") == []


def test_tracker_version_up_only_for_opened_workfile(monkeypatch):
    from ayon_core.pipeline.workfile import utils

    calls = []
    monkeypatch.setattr(utils, "save_next_version", lambda: calls.append(1))
    host = _MockHost()
    tracker = TaskUsageTracker(host)

    tracker._version_up("other_v001.ma")
    assert calls == []

    tracker._version_up("sh010_anim_v001.ma")
    assert calls == [1]
