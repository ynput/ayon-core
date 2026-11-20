"""Test task in-use tracking in the pipeline module."""
from __future__ import annotations

import ast
import datetime
import inspect
import re
import threading
from typing import Any

import pytest

from ayon_core.host import IWorkfileHost, WorkfileInUse
from ayon_core.pipeline.workfile import task_usage
from ayon_core.pipeline.workfile.task_usage import (
    TaskUsageItem,
    TaskUsageSettings,
    TaskUsageTracker,
    filter_other_users_items,
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
    host_name: str | None = "maya",
    hours_ago: float = 0.0,
    opened_hours_ago: float | None = None,
) -> TaskUsageItem:
    if opened_hours_ago is None:
        opened_hours_ago = hours_ago
    updated_at = NOW - datetime.timedelta(hours=hours_ago)
    opened_at = NOW - datetime.timedelta(hours=opened_hours_ago)
    return TaskUsageItem(
        session_id=session_id,
        username=username,
        machine="machine",
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
        "hostName": item.host_name,
        "workfile": item.workfile,
        "openedAt": item.opened_at,
        "updatedAt": item.updated_at,
        "fullName": item.full_name,
    }


def test_item_data_roundtrip():
    item = _item()
    assert TaskUsageItem.from_server_data(_server_data(item)) == item
    assert TaskUsageItem.from_data(item.to_data()) == item


def test_item_to_server_data():
    """Username and times are filled by the server."""
    assert _item().to_server_data() == {
        "machine": "machine",
        "hostName": "maya",
        "workfile": "sh010_anim_v001.ma",
    }


def test_filter_other_users_items():
    mine = _item("mine-other-host", host_name="nuke")
    other = _item("other", username="artist2")
    assert filter_other_users_items([mine, other], "artist1") == [other]
    # User was already notified about the session
    assert filter_other_users_items(
        [mine, other], "artist1", {"other"}
    ) == []


def _settings(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    workfiles = {"task_in_use_profiles": profiles}
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
    project_settings = _settings([])
    settings = get_task_usage_settings(
        "project", "maya", "Animation", "anim", project_settings
    )
    assert settings == TaskUsageSettings(enabled=False)
    assert not is_task_usage_enabled_in_project("project", project_settings)


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


@pytest.mark.parametrize(
    "minutes, ttl",
    [
        (5.0, 300),
        (2.5, 150),
        # Limits of the settings
        (1.0, 60),
        (60.0, 3600),
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
            "hostName": kwargs["hostName"],
            "workfile": kwargs["workfile"],
            "openedAt": opened_at,
            "updatedAt": updated_at,
            "fullName": None,
        }
        return _Response(data={
            "sessions": self._task_sessions(task_id),
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

    monkeypatch.setattr(task_usage, "_get_now", lambda: NOW)
    monkeypatch.setattr(task_usage, "_get_session_id", lambda: "mine")
    monkeypatch.setattr(task_usage, "get_ayon_username", lambda: "artist1")
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())

    def _raw_request(method):
        def _request(endpoint, json=None, timeout=None):
            # Callbacks of the application must not wait for long
            assert timeout == task_usage.REQUEST_TIMEOUT_SECONDS
            return getattr(mock_server, method)(endpoint, **(json or {}))
        return _request

    for method in ("get", "put", "delete"):
        monkeypatch.setattr(
            task_usage.ayon_api, f"raw_{method}", _raw_request(method)
        )
    return mock_server


def test_claim_update_and_release(server):
    other = _item("other", username="artist3")
    server.add("task-id", other)

    item = task_usage.create_session_item("file.ma", "maya", "mine")
    assert task_usage.claim_task("project", "task-id", item, 120) == [other]
    assert server.requests == [(
        "put",
        f"{ENDPOINT}/task-id/mine",
        {
            "ttl": 120,
            "heartbeat": False,
            "machine": item.machine,
            "hostName": "maya",
            "workfile": "file.ma",
        },
    )]
    assert set(server.sessions["task-id"]) == {"other", "mine"}

    server.now = NOW + datetime.timedelta(hours=1)
    task_usage.claim_task(
        "project", "task-id", item, 120, heartbeat=True
    )
    assert server.requests[-1][2]["heartbeat"] is True
    session = server.sessions["task-id"]["mine"]
    assert session["openedAt"] == session["updatedAt"] == NOW.isoformat()

    task_usage.claim_task("project", "task-id", item, 300)
    assert server.requests[-1][2]["ttl"] == 300
    session = server.sessions["task-id"]["mine"]
    assert session["openedAt"] == NOW.isoformat()
    assert session["updatedAt"] == server.now.isoformat()

    task_usage.release_task("project", "task-id", "mine")
    assert server.requests[-1][:2] == (
        "delete", f"{ENDPOINT}/task-id/mine"
    )
    assert set(server.sessions["task-id"]) == {"other"}


def test_get_task_usage_items(server):
    mine = _item("mine")
    other = _item("other", username="artist2")
    server.add("task-id", mine, other)

    assert task_usage.get_task_usage_items("project", "task-id") == [
        mine, other
    ]
    assert task_usage.get_task_usage_items("project", "unused") == []


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


def test_server_error_is_raised(server):
    server.status_code = 500
    with pytest.raises(RuntimeError):
        task_usage.get_task_usage_items("project", "task-id")

    server.status_code = 200
    task_usage.get_task_usage_items("project", "task-id")
    assert len(server.requests) == 2


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


def _claim_call_name(
    claimed: set[tuple[str, str]],
    task_id: str,
    item: TaskUsageItem,
    heartbeat: bool,
) -> str:
    """Name of claim request: claim, update or heartbeat."""
    key = (task_id, item.session_id)
    if heartbeat:
        return "heartbeat"
    if key in claimed:
        return "update"
    claimed.add(key)
    return "claim"


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
    claimed = set()

    def _claim_task(project_name, task_id, item, ttl, heartbeat=False):
        name = _claim_call_name(claimed, task_id, item, heartbeat)
        calls.append((name, task_id, item.workfile))
        if task_id == "in-use":
            return [other_user]
        return []

    def _release_task(project_name, task_id, session_id):
        claimed.discard((task_id, session_id))
        calls.append(("release", task_id, session_id))

    _mock_task_context(tracker, monkeypatch)
    monkeypatch.setattr(task_usage, "_notice_callbacks", [notices.append])
    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
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
    tracker.stop()
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
    (items,) = notices
    assert [item.session_id for item in items] == ["other-user"]
    # User is not notified or asked about the sessions again
    assert task_usage._acknowledged_session_ids == {"other-user"}


def test_tracker_notice_without_frontend(tracker_calls, monkeypatch):
    """User is asked in the Workfiles tool if nothing shows the notice."""
    host, tracker, calls, notices = tracker_calls

    def _failing(items):
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

    tracker.stop()
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

    monkeypatch.setattr(task_usage, "claim_task", claim_task)
    tracker.process()
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Failed heartbeat is not repeated immediately
    monkeypatch.setattr(task_usage, "claim_task", _failing)
    current_time[0] += interval
    tracker.process()
    assert len(failed_calls) == 4
    assert tracker._get_wait_seconds() == interval

    monkeypatch.setattr(task_usage, "release_task", _failing)
    tracker.stop()
    assert len(failed_calls) == 5


def test_tracker_thread(tracker_calls, monkeypatch):
    """Scheduled context is processed and released by the thread.

    Host integration is used only in the main thread, the thread does
    only requests to the server.
    """
    host, tracker, calls, _ = tracker_calls
    main_thread = threading.current_thread()
    threads = []
    host_threads = set()

    def _host_method(method):
        def _wrapper():
            host_threads.add(threading.current_thread())
            return method()
        return _wrapper

    for name in ("get_current_context", "get_current_workfile"):
        setattr(host, name, _host_method(getattr(host, name)))
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

    tracker.stop()
    assert not thread.is_alive()
    assert tracker._thread is None
    assert calls == [
        ("claim", "anim", "sh010_anim_v001.ma"),
        ("release", "anim", "mine"),
    ]
    assert threads == [thread, thread]
    assert main_thread not in threads
    assert host_threads == {main_thread}


def test_tracker_stop_during_request(tracker_calls, monkeypatch):
    """Release is sent when the thread is stopped during a request."""
    host, tracker, calls, _ = tracker_calls
    in_request = threading.Event()
    finish_request = threading.Event()
    claim_task = task_usage.claim_task

    def _claim_task(*args):
        in_request.set()
        finish_request.wait(5)
        return claim_task(*args)

    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    monkeypatch.setattr(task_usage, "EXIT_TIMEOUT_SECONDS", 0.05)
    tracker.start()
    thread = tracker._thread
    tracker.sync()
    assert in_request.wait(5)
    tracker.stop()

    finish_request.set()
    thread.join(5)
    assert not thread.is_alive()
    assert calls == [
        ("claim", "anim", "sh010_anim_v001.ma"),
        ("release", "anim", "mine"),
    ]


def test_tracker_stop_does_not_wait_for_server(tracker_calls, monkeypatch):
    """Exit of the application is not blocked by slow server."""
    host, tracker, calls, _ = tracker_calls
    release_started = threading.Event()
    finish_release = threading.Event()

    def _release_task(*args):
        release_started.set()
        finish_release.wait(5)

    monkeypatch.setattr(task_usage, "release_task", _release_task)
    monkeypatch.setattr(task_usage, "EXIT_TIMEOUT_SECONDS", 0.05)
    _sync(tracker)
    tracker.start()
    thread = tracker._thread
    tracker.stop()
    # Thread is still releasing the task
    assert release_started.wait(5)
    assert thread.is_alive()

    # Nothing happens in current thread when exit is called again
    tracker.stop()

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
    assert tracker._sessions == {}


def _prepare_install(monkeypatch):
    started = []
    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: False)
    monkeypatch.setattr(task_usage, "is_in_tests", lambda: False)
    monkeypatch.setattr(
        task_usage, "is_task_usage_enabled_in_project", lambda *args: True
    )
    for key in task_usage.FARM_JOB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(task_usage, "register_event_callback", lambda *a: None)
    monkeypatch.setattr(task_usage.atexit, "register", lambda *a: None)
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
    assert started == ["sync", "start"]


def test_tracker_install_follows_host_events(monkeypatch):
    """Opened workfiles are synced when the host changes them.

    E.g. Blender can't tell current workfile while it is installed, the
    first workfile is known on 'new' or 'open' event.
    """
    _prepare_install(monkeypatch)
    topics = []
    monkeypatch.setattr(
        task_usage,
        "register_event_callback",
        lambda topic, callback: topics.append(topic),
    )
    task_usage.install_task_usage_tracker(_MockHost())
    assert {"taskChanged", "new", "open", "save"}.issubset(topics)


def test_tracker_uninstall(monkeypatch):
    _prepare_install(monkeypatch)
    stopped = []
    monkeypatch.setattr(
        TaskUsageTracker, "stop", lambda self: stopped.append(self)
    )
    unregistered = []
    monkeypatch.setattr(task_usage.atexit, "unregister", unregistered.append)
    tracker = task_usage.install_task_usage_tracker(_MockHost())
    task_usage._on_exit()
    task_usage.uninstall_task_usage_tracker()
    task_usage.uninstall_task_usage_tracker()
    task_usage._on_exit()
    assert stopped == [tracker] * 2
    # Exit callback is not registered more times on next install
    assert unregistered == [task_usage._on_exit]


def test_no_qt_or_tools_imports():
    """Pipeline logic does not import Qt or tools, not all hosts use Qt.

    Host integration does register a frontend of notices on its own.
    """
    tree = ast.parse(inspect.getsource(task_usage))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    qt_modules = {"qtpy", "PySide2", "PySide6", "PyQt5", "PyQt6"}
    assert not [
        module
        for module in modules
        if module.split(".")[0] in qt_modules
        or module.startswith("ayon_core.tools")
    ]


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


def test_endpoint():
    from ayon_core.version import __version__

    base = f"addons/core/{__version__}/projects/my_project/taskInUse"
    assert task_usage._get_endpoint("my_project") == base
    assert task_usage._get_endpoint("my_project", "query") == f"{base}/query"
    assert task_usage._get_endpoint(
        "my_project", "task-id", "session-id"
    ) == f"{base}/task-id/session-id"


class _MultiWorkfilesHost(_MockHost):
    """Host integration with more workfiles opened at the same time."""

    def __init__(self):
        super().__init__()
        self.workfiles_in_use = []

    def add(self, key, task_name, filename):
        self.workfiles_in_use.append(WorkfileInUse(
            "project", "/shots/sh010", task_name, f"/path/{filename}", key
        ))

    def get_workfiles_in_use(self):
        return list(self.workfiles_in_use)


@pytest.fixture
def multi_tracker(tracker_calls, monkeypatch):
    """Tracker of host with more opened workfiles.

    Calls contain session id instead of the workfile.
    """
    _, _, calls, notices = tracker_calls
    host = _MultiWorkfilesHost()
    tracker = TaskUsageTracker(host)
    _mock_task_context(tracker, monkeypatch)

    claimed = set()

    def _claim_task(project_name, task_id, item, ttl, heartbeat=False):
        name = _claim_call_name(claimed, task_id, item, heartbeat)
        calls.append((name, task_id, item.session_id, item.workfile))
        if task_id == "in-use":
            return [_item("other-user", username="artist2")]
        return []

    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    return host, tracker, calls, notices


def test_workfile_session_id():
    process_id = task_usage._get_session_id()
    assert task_usage.get_workfile_session_id() == process_id
    session_id = task_usage.get_workfile_session_id("document 1 / ž")
    assert session_id != task_usage.get_workfile_session_id("document 2")
    assert session_id == task_usage.get_workfile_session_id("document 1 / ž")
    # Session id is valid for the server
    assert re.match(r"^[a-zA-Z0-9_-]{1,64}$", session_id)


def test_default_workfiles_in_use():
    """Default implementation is current workfile in current context."""
    host = _MockHost()
    assert IWorkfileHost.get_workfiles_in_use(host) == [
        WorkfileInUse(
            "project", "/shots/sh010", "anim", "/path/sh010_anim_v001.ma"
        )
    ]
    host.workfile = None
    (workfile_in_use,) = IWorkfileHost.get_workfiles_in_use(host)
    assert workfile_in_use.filepath is None
    assert workfile_in_use.key == ""


def test_tracker_host_with_more_workfiles(multi_tracker, monkeypatch):
    host, tracker, calls, _ = multi_tracker
    monkeypatch.setattr(task_usage, "_get_session_id", lambda: "mine")
    doc_1 = task_usage.get_workfile_session_id("doc-1")
    doc_2 = task_usage.get_workfile_session_id("doc-2")
    doc_3 = task_usage.get_workfile_session_id("doc-3")

    # Two workfiles of the same task and one of a different task
    host.add("doc-1", "anim", "sh010_anim_v001.ma")
    host.add("doc-2", "anim", "sh010_anim_v002.ma")
    host.add("doc-3", "layout", "sh010_layout_v001.ma")
    _sync(tracker)
    assert calls == [
        ("claim", "anim", doc_1, "sh010_anim_v001.ma"),
        ("claim", "anim", doc_2, "sh010_anim_v002.ma"),
        ("claim", "layout", doc_3, "sh010_layout_v001.ma"),
    ]

    # A workfile is saved under a different name, its session is kept
    host.workfiles_in_use[1] = WorkfileInUse(
        "project", "/shots/sh010", "anim", "/path/sh010_anim_v003.ma", "doc-2"
    )
    _sync(tracker)
    assert calls[3:] == [("update", "anim", doc_2, "sh010_anim_v003.ma")]

    # A workfile is closed, the other workfile of the task stays
    del host.workfiles_in_use[0]
    _sync(tracker)
    assert calls[4:] == [("release", "anim", doc_1)]

    # A workfile is saved to a different task
    host.workfiles_in_use[0] = WorkfileInUse(
        "project", "/shots/sh010", "comp", "/path/sh010_comp_v001.ma", "doc-2"
    )
    _sync(tracker)
    assert calls[5:] == [
        ("release", "anim", doc_2),
        ("claim", "comp", doc_2, "sh010_comp_v001.ma"),
    ]

    # All workfiles are released when the application is closed
    tracker.stop()
    assert sorted(calls[7:]) == [
        ("release", "comp", doc_2),
        ("release", "layout", doc_3),
    ]
    assert tracker._sessions == {}


def test_tracker_host_without_workfiles(multi_tracker):
    """Host integration can disable the tracking."""
    host, tracker, calls, _ = multi_tracker

    _sync(tracker)
    assert calls == []

    host.add("doc-1", "anim", "sh010_anim_v001.ma")
    _sync(tracker)
    host.workfiles_in_use = []
    _sync(tracker)
    assert [call[0] for call in calls] == ["claim", "release"]


def test_tracker_heartbeat_of_more_workfiles(multi_tracker, current_time):
    host, tracker, calls, _ = multi_tracker
    interval = TaskUsageSettings(True).heartbeat_interval

    host.add("doc-1", "anim", "sh010_anim_v001.ma")
    _sync(tracker)
    current_time[0] += interval / 2
    host.add("doc-2", "layout", "sh010_layout_v001.ma")
    _sync(tracker)
    assert [call[0] for call in calls] == ["claim", "claim"]
    # First workfile needs a heartbeat sooner
    assert tracker._get_wait_seconds() == interval / 2

    current_time[0] += interval / 2
    tracker.process()
    assert [call[:2] for call in calls[2:]] == [("heartbeat", "anim")]
    assert tracker._get_wait_seconds() == interval / 2

    current_time[0] += interval / 2
    tracker.process()
    assert [call[:2] for call in calls[3:]] == [("heartbeat", "layout")]


def test_tracker_notifies_once_about_other_users(multi_tracker):
    """Two workfiles of a task in use are claimed at the same time."""
    host, tracker, calls, notices = multi_tracker

    host.add("doc-1", "in-use", "sh010_anim_v001.ma")
    host.add("doc-2", "in-use", "sh010_anim_v002.ma")
    _sync(tracker)
    assert [call[0] for call in calls] == ["claim", "claim"]
    assert len(notices) == 1


def test_sync_task_usage(monkeypatch):
    calls = []
    monkeypatch.setattr(task_usage, "_tracker", None)
    # Tracking is not installed
    task_usage.sync_task_usage()

    tracker = TaskUsageTracker(_MockHost())
    monkeypatch.setattr(tracker, "sync", lambda: calls.append(1))
    monkeypatch.setattr(task_usage, "_tracker", tracker)
    task_usage.sync_task_usage()
    assert calls == [1]


def test_tracker_install_skipped_if_not_used_in_project(monkeypatch):
    """Nothing is started if the project does not have enabled profile."""
    started = _prepare_install(monkeypatch)
    projects = []

    def _is_enabled(project_name, *args):
        projects.append(project_name)
        return False

    monkeypatch.setattr(
        task_usage, "is_task_usage_enabled_in_project", _is_enabled
    )
    assert task_usage.install_task_usage_tracker(_MockHost()) is None
    assert projects == ["project"]

    # Host integration without a project
    host = _MockHost()
    host.get_current_context = lambda: {"project_name": None}
    assert task_usage.install_task_usage_tracker(host) is None
    assert projects == ["project"]

    # Failing host integration or settings
    def _failing():
        raise KeyError("AYON_PROJECT_NAME")

    host.get_current_context = _failing
    assert task_usage.install_task_usage_tracker(host) is None
    assert started == []
