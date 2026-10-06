"""Test task in-use tracking in the pipeline module."""
from __future__ import annotations

import datetime
from typing import Any, Optional

import pytest

from ayon_core.pipeline.workfile import task_usage
from ayon_core.pipeline.workfile.task_usage import (
    TASK_USAGE_DATA_KEY,
    TaskUsageItem,
    TaskUsageSettings,
    TaskUsageTracker,
    add_session_item,
    filter_active_items,
    filter_other_users_items,
    get_task_usage_settings,
    parse_task_usage_items,
    remove_session_item,
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


def test_item_data_roundtrip():
    item = _item()
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
    assert parse_task_usage_items(None) == []
    assert parse_task_usage_items({}) == []
    assert parse_task_usage_items({TASK_USAGE_DATA_KEY: {"a": 1}}) == []
    assert parse_task_usage_items(
        {TASK_USAGE_DATA_KEY: [item.to_data(), {"invalid": True}]}
    ) == [item]


def test_filter_active_items():
    active = _item("active", hours_ago=7.5)
    stale = _item("stale", hours_ago=8.5)
    assert filter_active_items([active, stale], 8.0, now=NOW) == [active]


def test_add_session_item_keeps_other_users():
    other = _item("other", username="artist2")
    new_item = _item("mine")
    assert add_session_item([other], new_item) == [other, new_item]


def test_add_session_item_keeps_opened_time():
    existing = _item("mine", hours_ago=1, opened_hours_ago=3)
    output = add_session_item([existing], _item("mine"))
    assert len(output) == 1
    assert output[0].opened_at == existing.opened_at
    assert output[0].updated_at == NOW.isoformat()


def test_add_session_item_replaces_crashed_session():
    crashed = _item("crashed", hours_ago=2)
    other_host = _item("nuke-session", host_name="nuke")
    other_site = _item("other-site", site_id="site-2")
    new_item = _item("mine")
    output = add_session_item([crashed, other_host, other_site], new_item)
    assert output == [other_host, other_site, new_item]


def test_remove_session_item():
    mine = _item("mine")
    other = _item("other", username="artist2")
    assert remove_session_item([mine, other], "mine") == [other]


def test_filter_other_users_items():
    mine = _item("mine-other-host", host_name="nuke")
    other = _item("other", username="artist2")
    assert filter_other_users_items([mine, other], "artist1") == [other]
    # Session of current process on the task does not hide other users
    assert filter_other_users_items(
        [_item("session"), other], "artist1"
    ) == [other]
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


def test_tracker_install_uses_acknowledged_env(monkeypatch):
    acknowledged = set()
    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", acknowledged)
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: False)
    monkeypatch.setattr(task_usage, "is_in_tests", lambda: False)
    monkeypatch.delenv("AYON_REMOTE_PUBLISH", raising=False)
    monkeypatch.setenv(task_usage.ACKNOWLEDGED_SESSIONS_ENV_KEY, "a,b,")
    monkeypatch.setattr(task_usage, "register_event_callback", lambda *a: None)
    monkeypatch.setattr(task_usage.atexit, "register", lambda *a: None)
    monkeypatch.setattr(task_usage, "_connect_qt_quit", lambda: None)
    monkeypatch.setattr(TaskUsageTracker, "sync", lambda self: None)

    assert task_usage.install_task_usage_tracker(_MockHost()) is not None
    assert acknowledged == {"a", "b"}


def test_tracker_install_skipped_in_headless(monkeypatch):
    monkeypatch.setattr(task_usage, "_tracker", None)
    monkeypatch.setattr(task_usage, "is_headless_mode_enabled", lambda: True)
    assert task_usage.install_task_usage_tracker(_MockHost()) is None


def _settings(profiles: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    workfiles = {}
    if profiles is not None:
        workfiles["task_in_use_profiles"] = profiles
    return {"core": {"tools": {"Workfiles": workfiles}}}


def test_settings_disabled_by_default():
    for profiles in (None, []):
        settings = get_task_usage_settings(
            "project", "maya", "Animation", "anim", _settings(profiles)
        )
        assert settings == TaskUsageSettings(enabled=False)


def test_settings_profile_filtering():
    project_settings = _settings([
        {
            "host_names": ["maya"],
            "task_types": [],
            "task_names": [],
            "enabled": True,
            "stale_timeout_hours": 2.0,
        }
    ])
    settings = get_task_usage_settings(
        "project", "maya", "Animation", "anim", project_settings
    )
    assert settings == TaskUsageSettings(True, 2.0)

    settings = get_task_usage_settings(
        "project", "nuke", "Compositing", "comp", project_settings
    )
    assert settings.enabled is False


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
def tracker_calls(monkeypatch):
    """Tracker with mocked server calls.

    Task id is the same as task name, task 'disabled' does not have enabled
    in-use tracking.
    """
    calls = []
    host = _MockHost()
    tracker = TaskUsageTracker(host)
    other_user = _item("other-user", username="artist2")

    def _query_task_context(project_name, folder_path, task_name):
        if task_name == "disabled":
            return None
        return task_usage._TaskContext(
            project_name, task_name, TaskUsageSettings(True)
        )

    def _claim_task(project_name, task_id, *, workfile, **kwargs):
        calls.append(("claim", task_id, workfile))
        if task_id == "in-use":
            return [other_user, _item("mine")]
        return [_item("mine")]

    def _notify(items):
        calls.append(("notify", [item.session_id for item in items]))

    def _release_task(project_name, task_id, **kwargs):
        calls.append(("release", task_id))

    monkeypatch.setattr(tracker, "_query_task_context", _query_task_context)
    monkeypatch.setattr(tracker, "_notify", _notify)
    monkeypatch.setattr(task_usage, "get_ayon_username", lambda: "artist1")
    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(task_usage, "claim_task", _claim_task)
    monkeypatch.setattr(task_usage, "release_task", _release_task)
    return host, tracker, calls


def test_tracker_claims_and_releases(tracker_calls):
    host, tracker, calls = tracker_calls

    tracker.sync()
    assert calls == [("claim", "anim", "sh010_anim_v001.ma")]

    # Nothing did change
    tracker.sync()
    assert len(calls) == 1

    # Workfile did change
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()
    assert calls[1:] == [("claim", "anim", "sh010_anim_v002.ma")]

    # Task did change
    host.task_name = "layout"
    tracker.sync()
    assert calls[2:] == [
        ("release", "anim"),
        ("claim", "layout", "sh010_anim_v002.ma"),
    ]

    # Task without enabled tracking
    host.task_name = "disabled"
    tracker.sync()
    assert calls[4:] == [("release", "layout")]

    # Nothing is claimed
    tracker.release()
    assert len(calls) == 5


def test_tracker_notifies_about_other_users(tracker_calls):
    host, tracker, calls = tracker_calls

    host.task_name = "in-use"
    tracker.sync()
    assert calls == [
        ("claim", "in-use", "sh010_anim_v001.ma"),
        ("notify", ["other-user"]),
    ]

    # User is notified only once about the same session
    host.workfile = "/path/sh010_anim_v002.ma"
    tracker.sync()
    assert calls[2:] == [("claim", "in-use", "sh010_anim_v002.ma")]


def test_tracker_skips_acknowledged_users(tracker_calls):
    """Sessions confirmed in the Workfiles tool are not notified again."""
    host, tracker, calls = tracker_calls

    task_usage.acknowledge_task_usage_items(
        [_item("other-user", username="artist2")]
    )
    host.task_name = "in-use"
    tracker.sync()
    assert calls == [("claim", "in-use", "sh010_anim_v001.ma")]


def test_tracker_refreshes_after_interval(tracker_calls, monkeypatch):
    host, tracker, calls = tracker_calls
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
    assert len(calls) == 2


def test_tracker_does_not_raise(tracker_calls, monkeypatch):
    host, tracker, calls = tracker_calls

    def _failing(*args, **kwargs):
        raise RuntimeError("Server is not available")

    monkeypatch.setattr(task_usage, "claim_task", _failing)
    tracker.sync()

    monkeypatch.setattr(task_usage, "claim_task", lambda *a, **k: None)
    monkeypatch.setattr(task_usage, "release_task", _failing)
    tracker.sync()
    tracker.release()


def test_update_task_usage(monkeypatch):
    """Whole task data are sent and stale sessions are removed."""
    stale = _item("stale", username="artist2", hours_ago=10)
    other = _item("other", username="artist3")
    task_data = {
        "custom": "value",
        TASK_USAGE_DATA_KEY: [stale.to_data(), other.to_data()],
    }
    updates = []

    monkeypatch.setattr(task_usage, "_get_now", lambda: NOW)
    monkeypatch.setattr(task_usage, "_get_session_id", lambda: "mine")
    monkeypatch.setattr(task_usage, "get_ayon_username", lambda: "artist1")
    monkeypatch.setattr(task_usage, "get_local_site_id", lambda: "site-1")
    monkeypatch.setattr(
        task_usage.ayon_api,
        "get_task_by_id",
        lambda *args, **kwargs: {"id": "task-id", "data": dict(task_data)},
    )
    monkeypatch.setattr(
        task_usage.ayon_api,
        "update_task",
        lambda project_name, task_id, data: updates.append(data),
    )

    task_usage.claim_task(
        "project", "task-id", workfile="file.ma", host_name="maya"
    )
    assert len(updates) == 1
    assert updates[0]["custom"] == "value"
    sessions = updates[0][TASK_USAGE_DATA_KEY]
    assert [session["session_id"] for session in sessions] == [
        "other", "mine"
    ]

    # Release of session that is not on the task does not update the task
    task_data[TASK_USAGE_DATA_KEY] = [other.to_data()]
    task_usage.release_task("project", "task-id")
    assert len(updates) == 1
