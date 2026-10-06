"""Test task in-use tracking in the pipeline module."""
from __future__ import annotations

import datetime
from typing import Any, Optional

import pytest

from ayon_core.pipeline.workfile import task_usage
from ayon_core.pipeline.workfile.task_usage import (
    TASK_USAGE_KEY_PREFIX,
    TaskUsageItem,
    TaskUsageSettings,
    TaskUsageTracker,
    filter_active_items,
    filter_other_users_items,
    get_task_usage_cleanup_keys,
    get_task_usage_settings,
    is_task_usage_enabled_in_project,
    parse_task_usage_items,
)

NOW = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)


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


def _task_data(*items: TaskUsageItem, **kwargs: Any) -> dict[str, Any]:
    data = {item.data_key: item.to_data() for item in items}
    data.update(kwargs)
    return data


def test_item_data_roundtrip():
    item = _item()
    assert item.data_key == f"{TASK_USAGE_KEY_PREFIX}session-1"
    assert TaskUsageItem.from_data(item.to_data()) == item


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


def test_parse_task_usage_items():
    item = _item()
    other = _item("other")
    assert parse_task_usage_items(None) == []
    assert parse_task_usage_items({}) == []
    assert parse_task_usage_items({"custom": {"session_id": "a"}}) == []
    task_data = _task_data(item, other, custom="value")
    # Invalid session data
    task_data[f"{TASK_USAGE_KEY_PREFIX}invalid"] = {"invalid": True}
    # Session stored under a key of different session
    task_data[f"{TASK_USAGE_KEY_PREFIX}wrong"] = _item("moved").to_data()
    assert parse_task_usage_items(task_data) == [item, other]


def test_filter_active_items():
    active = _item("active", hours_ago=7.5)
    stale = _item("stale", hours_ago=8.5)
    assert filter_active_items([active, stale], 8.0, now=NOW) == [active]


def test_cleanup_keys():
    new_item = _item("mine")
    other_user = _item("other-user", username="artist2")
    other_host = _item("other-host", host_name="nuke")
    other_site = _item("other-site", site_id="site-2")
    crashed = _item("crashed", hours_ago=2)
    stale = _item("stale", username="artist3", hours_ago=10)
    task_data = _task_data(
        new_item, other_user, other_host, other_site, crashed, stale,
        custom="value",
    )
    invalid_key = f"{TASK_USAGE_KEY_PREFIX}invalid"
    task_data[invalid_key] = "invalid"

    assert get_task_usage_cleanup_keys(
        task_data, new_item, 8.0, now=NOW
    ) == {crashed.data_key, stale.data_key, invalid_key}
    assert get_task_usage_cleanup_keys(None, new_item, 8.0, now=NOW) == set()


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
        "stale_timeout_hours": 2.0,
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


@pytest.fixture
def server(monkeypatch):
    """Mocked server calls.

    Returns:
        tuple[dict[str, Any], list[dict[str, Any]]]: Task data on the
            server and data of sent updates.

    """
    task_data = {"custom": "value"}
    updates = []

    def _get_task_by_id(project_name, task_id, fields=None):
        return {"id": task_id, "data": dict(task_data)}

    def _update_task(project_name, task_id, data):
        """Server merges top-level keys and removes keys with None."""
        updates.append(data)
        for key, value in data.items():
            if value is None:
                task_data.pop(key, None)
            else:
                task_data[key] = value

    monkeypatch.setattr(task_usage, "_get_now", lambda: NOW)
    monkeypatch.setattr(task_usage, "_get_session_id", lambda: "mine")
    monkeypatch.setattr(task_usage, "get_ayon_username", lambda: "artist1")
    monkeypatch.setattr(task_usage, "get_local_site_id", lambda: "site-1")
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(task_usage.ayon_api, "get_task_by_id", _get_task_by_id)
    monkeypatch.setattr(task_usage.ayon_api, "update_task", _update_task)
    return task_data, updates


def test_claim_update_and_release(server):
    task_data, updates = server
    stale = _item("stale", username="artist2", hours_ago=10)
    crashed = _item("crashed", hours_ago=1)
    other = _item("other", username="artist3")
    task_data.update(_task_data(stale, crashed, other))

    item = task_usage.create_session_item("file.ma", "maya")
    assert task_usage.claim_task("project", "task-id", item) == [other]
    # Only keys of sessions are sent
    assert updates == [{
        item.data_key: item.to_data(),
        stale.data_key: None,
        crashed.data_key: None,
    }]
    assert task_data == _task_data(other, item, custom="value")

    task_usage.update_task_session("project", "task-id", item)
    assert updates[1:] == [{item.data_key: item.to_data()}]

    task_usage.release_task("project", "task-id")
    assert updates[2:] == [{item.data_key: None}]
    assert task_data == _task_data(other, custom="value")


def test_other_users_task_usage_items(server):
    task_data, _ = server
    mine = _item("mine")
    other = _item("other", username="artist2")
    stale = _item("stale", username="artist3", hours_ago=10)
    task_data.update(_task_data(mine, other, stale))

    assert task_usage.get_other_users_task_usage_items(
        "project", "task-id"
    ) == [other]

    task_usage.acknowledge_task_usage_items([other])
    assert task_usage.get_other_users_task_usage_items(
        "project", "task-id"
    ) == []


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


@pytest.fixture
def tracker_calls(server, monkeypatch):
    """Tracker with mocked server calls.

    Task id is the same as task name, task 'disabled' does not have enabled
    in-use tracking. Task 'in-use' is in use by other user.
    """
    calls = []
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    other_user = _item("other-user", username="artist2")
    notice_shown = [True]

    def _query_task_context(project_name, folder_path, task_name):
        if task_name == "disabled":
            return None
        return task_usage._TaskContext(
            project_name, task_name, TaskUsageSettings(True)
        )

    def _claim_task(project_name, task_id, item, stale_timeout_hours):
        calls.append(("claim", task_id, item.workfile))
        if task_id == "in-use":
            return [other_user]
        return []

    def _update_task_session(project_name, task_id, item):
        calls.append(("update", task_id, item.workfile))

    def _release_task(project_name, task_id, session_id):
        calls.append(("release", task_id, session_id))

    def _notify(items):
        calls.append(("notify", [item.session_id for item in items]))
        return notice_shown[0]

    monkeypatch.setattr(tracker, "_query_task_context", _query_task_context)
    monkeypatch.setattr(tracker, "_notify", _notify)
    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    monkeypatch.setattr(
        task_usage, "update_task_session", _update_task_session
    )
    monkeypatch.setattr(task_usage, "release_task", _release_task)
    return host, tracker, calls, notice_shown


def test_tracker_claims_and_releases(tracker_calls):
    host, tracker, calls, _ = tracker_calls

    tracker.sync()
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Nothing did change
    tracker.sync()
    assert len(calls) == 1

    # Workfile did change, session is only updated
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()
    assert calls[1:] == [("update", "anim", "sh010_anim_v002.ma")]

    # Task did change
    host.task_name = "layout"
    tracker.sync()
    assert calls[2:] == [
        ("release", "anim", "mine"),
        ("claim", "layout", "sh010_anim_v002.ma"),
    ]

    # Task without enabled tracking
    host.task_name = "disabled"
    tracker.sync()
    assert calls[4:] == [("release", "layout", "mine")]

    # Nothing is claimed
    tracker.release()
    assert len(calls) == 5


def test_tracker_keeps_opened_time(server, monkeypatch):
    task_data, updates = server
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    monkeypatch.setattr(
        tracker,
        "_query_task_context",
        lambda *args: task_usage._TaskContext(
            "project", "task-id", TaskUsageSettings(True)
        ),
    )
    tracker.sync()

    later = NOW + datetime.timedelta(hours=1)
    monkeypatch.setattr(task_usage, "_get_now", lambda: later)
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()

    session = task_data[f"{TASK_USAGE_KEY_PREFIX}mine"]
    assert session["opened_at"] == NOW.isoformat()
    assert session["updated_at"] == later.isoformat()
    assert session["workfile"] == "sh010_anim_v002.ma"
    # Task data are read only when the task is claimed
    assert len(updates) == 2


def test_tracker_notifies_about_other_users(tracker_calls):
    host, tracker, calls, _ = tracker_calls

    host.task_name = "in-use"
    tracker.sync()
    assert calls == [
        ("claim", "in-use", "sh010_anim_v001.ma"),
        ("notify", ["other-user"]),
    ]
    assert task_usage._acknowledged_session_ids == {"other-user"}


def test_tracker_keeps_sessions_unconfirmed_without_notice(tracker_calls):
    """User is asked in the Workfiles tool if the notice was not shown."""
    host, tracker, calls, notice_shown = tracker_calls

    notice_shown[0] = False
    host.task_name = "in-use"
    tracker.sync()
    assert calls[-1] == ("notify", ["other-user"])
    assert task_usage._acknowledged_session_ids == set()


def test_tracker_skips_acknowledged_users(tracker_calls):
    """Sessions confirmed before are not notified again."""
    host, tracker, calls, _ = tracker_calls

    task_usage.acknowledge_task_usage_items(
        [_item("other-user", username="artist2")]
    )
    host.task_name = "in-use"
    tracker.sync()
    assert calls == [("claim", "in-use", "sh010_anim_v001.ma")]


def test_tracker_refreshes_after_interval(tracker_calls, monkeypatch):
    host, tracker, calls, _ = tracker_calls
    current_time = [1000.0]
    monkeypatch.setattr(
        task_usage.time, "monotonic", lambda: current_time[0]
    )

    tracker.sync()
    current_time[0] += task_usage.REFRESH_INTERVAL_SECONDS - 1
    tracker.sync()
    assert len(calls) == 1

    current_time[0] += 2
    tracker.sync()
    assert calls[1:] == [("update", "anim", "sh010_anim_v001.ma")]


def test_tracker_does_not_raise(tracker_calls, monkeypatch):
    host, tracker, calls, _ = tracker_calls

    current_time = [1000.0]
    monkeypatch.setattr(
        task_usage.time, "monotonic", lambda: current_time[0]
    )
    failed_calls = []

    def _failing(*args, **kwargs):
        failed_calls.append(1)
        raise RuntimeError("Server is not available")

    monkeypatch.setattr(task_usage, "claim_task", _failing)
    tracker.sync()
    # Failed update is not repeated with each sync
    tracker.sync()
    assert len(failed_calls) == 1

    current_time[0] += task_usage.REFRESH_INTERVAL_SECONDS + 1
    tracker.sync()
    assert len(failed_calls) == 2

    current_time[0] += task_usage.REFRESH_INTERVAL_SECONDS + 1
    monkeypatch.setattr(task_usage, "claim_task", lambda *a, **k: [])
    monkeypatch.setattr(task_usage, "release_task", _failing)
    tracker.sync()
    tracker.release()


def test_tracker_skips_queries_if_not_used_in_project(monkeypatch):
    def _failing(*args, **kwargs):
        raise AssertionError("Entities should not be queried")

    monkeypatch.setattr(
        task_usage, "get_project_settings", lambda *args: _settings([])
    )
    monkeypatch.setattr(task_usage.ayon_api, "get_folder_by_path", _failing)
    monkeypatch.setattr(task_usage.ayon_api, "get_task_by_id", _failing)

    tracker = TaskUsageTracker(_MockHost())
    tracker._sync()
    assert tracker._claimed is None


def _prepare_install(monkeypatch):
    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: False)
    monkeypatch.setattr(task_usage, "is_in_tests", lambda: False)
    for key in task_usage.FARM_JOB_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(task_usage, "register_event_callback", lambda *a: None)
    monkeypatch.setattr(task_usage.atexit, "register", lambda *a: None)
    monkeypatch.setattr(task_usage, "_connect_qt_quit", lambda: None)
    monkeypatch.setattr(TaskUsageTracker, "sync", lambda self: None)


def test_tracker_install_uses_acknowledged_env(monkeypatch):
    _prepare_install(monkeypatch)
    monkeypatch.setenv(task_usage.ACKNOWLEDGED_SESSIONS_ENV_KEY, "a,b,")

    assert task_usage.install_task_usage_tracker(_MockHost()) is not None
    assert task_usage._acknowledged_session_ids == {"a", "b"}


def test_tracker_install_skipped_in_headless(monkeypatch):
    _prepare_install(monkeypatch)
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: True)
    assert task_usage.install_task_usage_tracker(_MockHost()) is None


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
