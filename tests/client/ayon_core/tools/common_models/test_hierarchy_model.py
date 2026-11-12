"""Tests for hierarchy model."""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import Mock

import pytest

from ayon_core.tools.common_models import hierarchy
from ayon_core.tools.common_models.websocket import Event, EventCallback


def _rest_folder(
    folder_id: str,
    parent_id: str | None,
    path: str,
    active: bool | None = True,
) -> dict[str, Any]:
    """Flat folder item as returned by 'get_rest_folders'.

    Args:
        folder_id (str): Folder id.
        parent_id (str | None): Parent folder id.
        path (str): Folder path without leading slash.
        active (bool | None): Folder active state. 'None' leaves the key
            out, like older servers do.

    Returns:
        dict[str, Any]: Flat folder item.

    """
    folder = {
        "id": folder_id,
        "parentId": parent_id,
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "label": None,
        "folderType": "Folder",
        "status": "open",
    }
    if active is not None:
        folder["active"] = active
    return folder


class _FakeEventHub:
    """Event hub replacement which triggers callbacks directly."""

    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.callbacks: list[EventCallback] = []

    def is_connected(self) -> bool:
        return self.connected

    def add_callbacks(self, callbacks, *, connect=True) -> None:
        assert connect is False, "Cache must not create connection"
        self.callbacks.extend(callbacks)

    @property
    def topics(self) -> set[str]:
        return {callback.topic for callback in self.callbacks}

    def emit(self, topic: str, project_name: str | None = "demo", **kwargs):
        event = Event(topic=topic, project_name=project_name, **kwargs)
        for callback in self.callbacks:
            callback.process_event(event)


@pytest.fixture(autouse=True)
def shared_cache(monkeypatch) -> hierarchy._SharedFoldersCache:
    """Folder items cache is shared by all models, use new one per test."""
    cache = hierarchy._SharedFoldersCache()
    monkeypatch.setattr(hierarchy, "_SHARED_FOLDERS_CACHE", cache)
    monkeypatch.setattr(hierarchy, "get_existing_event_hub", lambda: None)
    return cache


@pytest.fixture
def event_hub(monkeypatch, shared_cache) -> _FakeEventHub:
    """Connected websocket listening to events since long time ago."""
    hub = _FakeEventHub()
    monkeypatch.setattr(hierarchy, "get_existing_event_hub", lambda: hub)
    # Don't wait for subscription to be sent
    monkeypatch.setattr(shared_cache, "subscribe_delay", 0)
    return hub


@pytest.fixture
def clock(monkeypatch, shared_cache) -> list[float]:
    """Controlled time of the shared folders cache."""
    now = [1000.0]
    monkeypatch.setattr(shared_cache, "_now", lambda: now[0])
    return now


@pytest.fixture
def get_folder_ids(monkeypatch):
    def _get_folder_ids(folders: list[dict[str, Any]]) -> set[str]:
        monkeypatch.setattr(
            hierarchy.ayon_api,
            "get_rest_folders",
            Mock(return_value=folders),
        )
        model = hierarchy.HierarchyModel(Mock())
        return set(model.get_folder_items("demo", None))
    return _get_folder_ids


def test_inactive_root_hides_descendants(get_folder_ids):
    folders = [
        _rest_folder("root", None, "root", active=False),
        _rest_folder("child", "root", "root/child"),
        _rest_folder("grandchild", "child", "root/child/grandchild"),
        _rest_folder("other", None, "other"),
    ]
    assert get_folder_ids(folders) == {"other"}


def test_inactive_nested_folder_hides_subtree(get_folder_ids):
    folders = [
        # Children listed before parents to not rely on response order
        _rest_folder("grandchild", "inactive", "root/inactive/grandchild"),
        _rest_folder("inactive", "root", "root/inactive", active=False),
        _rest_folder("sibling", "root", "root/sibling"),
        _rest_folder("root", None, "root"),
    ]
    assert get_folder_ids(folders) == {"root", "sibling"}


def test_missing_active_is_kept(get_folder_ids):
    folders = [
        _rest_folder("root", None, "root", active=None),
        _rest_folder("child", "root", "root/child", active=None),
    ]
    assert get_folder_ids(folders) == {"root", "child"}


@pytest.fixture
def get_rest_folders(monkeypatch) -> Mock:
    mock = Mock(return_value=[_rest_folder("root", None, "root")])
    monkeypatch.setattr(hierarchy.ayon_api, "get_rest_folders", mock)
    return mock


def test_folders_cache_is_shared_between_models(get_rest_folders):
    model_a = hierarchy.HierarchyModel(Mock())
    model_b = hierarchy.HierarchyModel(Mock())

    assert set(model_a.get_folder_items("demo", None)) == {"root"}
    assert set(model_b.get_folder_items("demo", None)) == {"root"}
    assert get_rest_folders.call_count == 1


def test_reset_keeps_shared_folders_cache(get_rest_folders):
    model_a = hierarchy.HierarchyModel(Mock())
    model_b = hierarchy.HierarchyModel(Mock())

    model_a.get_folder_items("demo", None)
    model_b.reset()
    model_b.get_folder_items("demo", None)
    assert get_rest_folders.call_count == 1


def test_forced_reset_clears_shared_folders_cache(get_rest_folders):
    model_a = hierarchy.HierarchyModel(Mock())
    model_b = hierarchy.HierarchyModel(Mock())

    model_a.get_folder_items("demo", None)
    model_b.reset(force=True)
    model_a.get_folder_items("demo", None)
    assert get_rest_folders.call_count == 2


def _get_folders(model: hierarchy.HierarchyModel) -> set[str]:
    return set(model.get_folder_items("demo", None))


def _query_count(get_rest_folders: Mock) -> int:
    return get_rest_folders.call_count


def test_without_websocket_uses_min_lifetime(
    get_rest_folders, shared_cache, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    clock[0] += shared_cache.min_lifetime - 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 1

    clock[0] += 2
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_listening_cache_is_kept_without_changes(
    get_rest_folders, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    clock[0] += 7 * 24 * 60 * 60
    _get_folders(model)
    assert _query_count(get_rest_folders) == 1

    # Refresh button
    model.reset(force=True)
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_subscribes_only_to_folder_items_topics(get_rest_folders, event_hub):
    _get_folders(hierarchy.HierarchyModel(Mock()))
    assert event_hub.topics == {
        "connection.opened",
        "connection.closed",
        *hierarchy._FOLDER_ITEMS_TOPICS,
        *hierarchy._PROJECT_TOPICS,
    }
    assert "entity.folder.attrib_changed" not in event_hub.topics


@pytest.mark.parametrize(
    "topic", hierarchy._FOLDER_ITEMS_TOPICS + hierarchy._PROJECT_TOPICS
)
def test_change_is_applied_after_min_lifetime(
    topic, get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    event_hub.emit(topic)

    # Folders are not queried more often than once per minimum lifetime
    clock[0] += shared_cache.min_lifetime - 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 1

    clock[0] += 2
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2

    # New result is kept as nothing changed since
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_change_in_other_project_is_ignored(
    get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    event_hub.emit("entity.folder.renamed", project_name="other")
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 1


def test_project_rename_invalidates_old_project_name(
    get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    # Server sends old project name only in summary
    event_hub.emit(
        "entity.project.renamed",
        project_name=None,
        summary={"entityName": "demo"},
    )
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_brief_connection_loss_keeps_folders(
    get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    clock[0] += 3 * shared_cache.min_lifetime

    # Brief interruption does not cause query
    event_hub.emit("connection.closed", project_name=None)
    event_hub.emit("connection.opened", project_name=None)
    _get_folders(model)
    clock[0] += shared_cache.min_lifetime - 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 1

    # Events might have been missed, query once
    clock[0] += 2
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2

    # Queried while connected
    clock[0] += 3 * shared_cache.min_lifetime
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_long_connection_loss_uses_min_lifetime(
    get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    event_hub.emit("connection.closed", project_name=None)

    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2

    # Queried while disconnected
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 3

    # Queried while connected
    event_hub.emit("connection.opened", project_name=None)
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 4
    clock[0] += 3 * shared_cache.min_lifetime
    _get_folders(model)
    assert _query_count(get_rest_folders) == 4


def test_known_change_is_not_extended_by_connection_loss(
    get_rest_folders, shared_cache, event_hub, clock
):
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    clock[0] += shared_cache.min_lifetime - 10
    event_hub.emit("entity.folder.renamed")
    event_hub.emit("connection.closed", project_name=None)
    clock[0] += 11
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_subscription_to_connected_websocket_waits(
    get_rest_folders, shared_cache, event_hub, clock
):
    shared_cache.subscribe_delay = 10
    model = hierarchy.HierarchyModel(Mock())
    # Subscription is not sent to server yet
    _get_folders(model)
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2

    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_change_during_query_is_not_ignored(
    get_rest_folders, shared_cache, event_hub, clock
):
    def _query(*_args, **_kwargs):
        if get_rest_folders.call_count == 1:
            event_hub.emit("entity.folder.created")
        return [_rest_folder("root", None, "root")]

    get_rest_folders.side_effect = _query
    model = hierarchy.HierarchyModel(Mock())
    _get_folders(model)
    clock[0] += shared_cache.min_lifetime + 1
    _get_folders(model)
    assert _query_count(get_rest_folders) == 2


def test_forced_reset_discards_running_query(get_rest_folders):
    query_started = threading.Event()
    release_query = threading.Event()

    def _query(*_args, **_kwargs):
        if get_rest_folders.call_count == 1:
            query_started.set()
            release_query.wait(5)
            return [_rest_folder("old", None, "old")]
        return [_rest_folder("new", None, "new")]

    get_rest_folders.side_effect = _query
    model_a = hierarchy.HierarchyModel(Mock())
    model_b = hierarchy.HierarchyModel(Mock())

    results = []
    thread = threading.Thread(
        target=lambda: results.append(_get_folders(model_a))
    )
    thread.start()
    assert query_started.wait(5)

    # User clicked refresh while other tool is querying folders
    model_b.reset(force=True)
    release_query.set()

    assert _get_folders(model_b) == {"new"}
    thread.join(5)
    assert results == [{"new"}]
    assert _query_count(get_rest_folders) == 2
