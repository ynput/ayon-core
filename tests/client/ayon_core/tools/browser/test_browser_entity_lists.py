"""Tests for the entity lists of the Browser's Reviews and Lists slicer."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.control import BrowserController
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
    _ListEntityIds,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory


@pytest.fixture(autouse=True)
def _mock_sitesync_addon(monkeypatch):
    # The Site Sync column provider looks up the addon on creation.
    addon_manager = Mock()
    addon_manager.get.return_value = None
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager",
        lambda: addon_manager,
    )


def _conditions(encoded: str) -> list:
    return json.loads(encoded)["conditions"] if encoded else []


def _lists_controller() -> BrowserWidgetController:
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    controller._current_category = BrowserSlicerCategory.LISTS.value
    controller._entity_lists_loaded = True
    return controller


def test_fetch_entity_lists_nests_lists_in_their_folders():
    controller = _lists_controller()
    controller._entity_list_folders_cache = [
        {
            "id": "f1",
            "label": "Dailies",
            "parentId": None,
            "data": {"icon": "movie", "color": "#ff0000"},
        },
        {"id": "f2", "label": "Week 1", "parentId": "f1", "data": {}},
        {"id": "f3", "label": "Empty", "parentId": None, "data": {}},
    ]
    controller._entity_lists_cache = [
        {
            "id": "review",
            "label": "Review",
            "entityType": "version",
            "entityListType": "review-session",
            "entityListFolderId": "f2",
            "createdAt": "2026-01-01",
        },
        {
            "id": "shots",
            "label": "Shots",
            "entityType": "folder",
            "entityListType": "generic",
            "entityListFolderId": "f1",
            "createdAt": "2026-01-02",
        },
        {
            "id": "old",
            "label": "Old",
            "entityType": "task",
            "entityListType": "generic",
            "createdAt": "2026-01-01",
        },
        {
            "id": "new",
            "label": "New",
            "entityType": "product",
            "entityListType": "generic",
            "entityListFolderId": "missing",
            "createdAt": "2026-01-03",
        },
        {
            "id": "archived",
            "label": "Archived",
            "entityType": "version",
            "entityListType": "generic",
            "active": False,
            "createdAt": "2026-01-04",
        },
    ]

    tree = controller.fetch_entity_lists()

    # Folders first, without the ones that hold no list. Lists of an
    # unknown folder are listed at the root, archived ones last.
    assert [
        (node.id, node.icon) for node in tree[None]
    ] == [
        ("folder-f1", "movie"),
        ("new", "inventory_2"),
        ("old", "check_circle"),
        ("archived", "layers"),
    ]
    folder = tree[None][0]
    assert folder.icon_color == "#ff0000"
    assert folder.icon_fill
    assert folder.has_children
    assert not folder.selectable
    assert [
        (node.id, node.icon) for node in tree["folder-f1"]
    ] == [
        ("folder-f2", "snippet_folder"),
        ("shots", "folder"),
    ]
    assert [
        (node.id, node.icon) for node in tree["folder-f2"]
    ] == [("review", "subscriptions")]


def test_reviews_only_hold_review_sessions_in_their_folders():
    controller = _lists_controller()
    controller._current_category = BrowserSlicerCategory.REVIEWS.value
    controller._entity_list_folders_cache = [
        {"id": "f1", "label": "Dailies", "parentId": None, "data": {}},
        {"id": "f2", "label": "Shots", "parentId": None, "data": {}},
    ]
    controller._entity_lists_cache = [
        {
            "id": "a",
            "label": "A",
            "entityListType": "review-session",
            "entityListFolderId": "f1",
        },
        {
            "id": "b",
            "label": "B",
            "entityListType": "generic",
            "entityListFolderId": "f2",
        },
        {"id": "c", "label": "C", "entityListType": "review-session"},
    ]

    tree = controller.fetch_entity_lists()

    # The folder holding only a generic list is left out.
    assert [node.id for node in tree[None]] == ["folder-f1", "c"]
    assert [node.id for node in tree["folder-f1"]] == ["a"]


def test_selected_lists_narrow_versions_by_their_entity_type(monkeypatch):
    controller = _lists_controller()
    items_by_list_id = {
        "versions": [("version", "v1"), ("version", "v2")],
        "products": [("product", "p1")],
        "folders": [("folder", "f1")],
        "tasks": [("task", "t1")],
    }

    def fake_get_entity_lists(project_name, list_ids, fields):
        for list_id in list_ids:
            yield {
                "items": [
                    {"entityType": entity_type, "entityId": entity_id}
                    for entity_type, entity_id in items_by_list_id[list_id]
                ]
            }

    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller.ayon_api"
        ".get_entity_lists",
        fake_get_entity_lists,
    )
    calls = []

    def fake_get_versions_page(*args, **kwargs):
        calls.append(kwargs)
        return [], {"hasNextPage": False, "endCursor": ""}

    monkeypatch.setattr(
        controller, "_get_versions_page", fake_get_versions_page
    )

    controller.on_tree_selection_changed(list(items_by_list_id))
    assert controller.has_selection
    controller.set_include_folder_children(True)
    controller.fetch_versions_page(0, 25)
    controller.set_include_folder_children(False)
    controller.fetch_versions_page(0, 25)

    assert [call["include_folder_children"] for call in calls] == [
        True,
        False,
    ]
    assert calls[0]["version_ids"] == ["v1", "v2"]
    assert calls[0]["product_ids"] == ["p1"]
    assert calls[0]["folder_ids"] == ["f1"]
    assert _conditions(calls[0]["task_filter"]) == [
        {"key": "id", "operator": "in", "value": ["t1"]}
    ]


def test_selected_empty_list_shows_no_versions(monkeypatch):
    controller = _lists_controller()
    monkeypatch.setattr(
        controller,
        "_get_entity_list_entity_ids",
        lambda list_ids: _ListEntityIds(),
    )
    get_versions_page = Mock()
    monkeypatch.setattr(controller, "_get_versions_page", get_versions_page)

    controller.on_tree_selection_changed(["empty"])

    assert controller.fetch_versions_page(0, 25) == []
    get_versions_page.assert_not_called()


def test_failing_list_items_request_shows_no_versions(monkeypatch):
    controller = _lists_controller()

    def failing_get_entity_lists(*args, **kwargs):
        raise ConnectionError("Server is not available")

    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller.ayon_api"
        ".get_entity_lists",
        failing_get_entity_lists,
    )

    controller.on_tree_selection_changed(["list"])

    assert not controller._list_entity_ids
    assert controller.fetch_versions_page(0, 25) == []


def test_project_change_clears_selected_list_entities(monkeypatch):
    controller = _lists_controller()
    controller._list_entity_ids = _ListEntityIds(version_ids=["v1"])
    monkeypatch.setattr(controller, "_ensure_entity_lists", Mock())
    monkeypatch.setattr(
        controller, "_get_cached_project_info", lambda project_name: None
    )
    monkeypatch.setattr(controller, "_request_project_info", Mock())

    controller.set_project("other_project")

    assert not controller._list_entity_ids
