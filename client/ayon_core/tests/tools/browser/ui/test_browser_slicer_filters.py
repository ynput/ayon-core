"""Tests for the extensible slicer-filter mechanism ("My Tasks" etc.)."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.control import LoaderController
from ayon_core.tools.browser.ui._browser_slicer_filters import (
    SlicerFiltersMenu,
)
from ayon_core.tools.browser.ui.browser_controller import BrowserController
from ayon_core.tools.browser.ui.browser_types import (
    MY_TASKS_FILTER_KEY,
    SLICER_FILTER_OPTIONS,
    BrowserSlicerCategory,
)
from ayon_core.tools.browser.ui.tasks_widget import (
    TASK_DATA_ROLE,
    BrowserTasksWidget,
)


@pytest.fixture(autouse=True)
def _mock_sitesync_model(monkeypatch):
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = []
    monkeypatch.setattr(
        "ayon_core.tools.browser.control.AddonsManager",
        lambda: addon_manager,
    )
    monkeypatch.setattr(
        "ayon_core.tools.browser.control.SiteSyncModel",
        lambda *args: Mock(),
    )


def _task_item(task_id, name, task_type="generic", task_type_order=0):
    return SimpleNamespace(
        task_id=task_id,
        name=name,
        task_type=task_type,
        task_type_order=task_type_order,
    )


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------


def test_my_tasks_option_only_offered_in_hierarchy():
    option = next(
        o for o in SLICER_FILTER_OPTIONS if o.key == MY_TASKS_FILTER_KEY
    )
    assert option.categories == (BrowserSlicerCategory.HIERARCHY,)


# ---------------------------------------------------------------------
# BrowserController scope resolution
# ---------------------------------------------------------------------


def test_set_slicer_filters_resolves_folder_and_task_scope(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"

    monkeypatch.setattr(
        controller._loader_controller,
        "get_my_tasks_entity_ids",
        lambda project_name: {
            "folder_ids": {"shot010"},
            "task_ids": {"task-1", "task-2"},
        },
    )
    monkeypatch.setattr(
        controller,
        "get_folder_id_path",
        lambda folder_id: ["episode", "sequence", folder_id],
    )
    reset_calls = Mock()
    controller.tree_reset_requested.connect(reset_calls)

    controller.set_slicer_filters({MY_TASKS_FILTER_KEY})

    assert controller._folder_id_scope == {
        "episode", "sequence", "shot010",
    }
    assert controller.get_task_id_scope() == {"task-1", "task-2"}
    reset_calls.assert_called_once()


def test_set_slicer_filters_noop_when_unchanged(monkeypatch):
    controller = BrowserController(LoaderController())
    recompute = Mock(wraps=controller._recompute_slicer_filter_scope)
    monkeypatch.setattr(
        controller, "_recompute_slicer_filter_scope", recompute
    )

    controller.set_slicer_filters(set())

    recompute.assert_not_called()


def test_set_slicer_filters_clears_scope_when_deselected(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    monkeypatch.setattr(
        controller._loader_controller,
        "get_my_tasks_entity_ids",
        lambda project_name: {
            "folder_ids": {"shot010"},
            "task_ids": {"task-1"},
        },
    )
    monkeypatch.setattr(
        controller, "get_folder_id_path", lambda folder_id: [folder_id]
    )
    controller.set_slicer_filters({MY_TASKS_FILTER_KEY})
    assert controller.get_task_id_scope() == {"task-1"}

    controller.set_slicer_filters(set())

    assert controller._folder_id_scope is None
    assert controller.get_task_id_scope() is None


def test_unknown_slicer_filter_key_has_no_effect():
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"

    controller.set_slicer_filters({"not_a_real_filter"})

    assert controller._folder_id_scope is None
    assert controller.get_task_id_scope() is None


def test_fetch_products_restricts_to_folder_id_scope(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._folder_id_scope = {"shot010"}

    monkeypatch.setattr(
        "ayon_api.get_folders",
        lambda project_name, parent_ids, fields: [
            {"id": "shot010", "name": "shot010", "parentId": None},
            {"id": "shot020", "name": "shot020", "parentId": None},
        ],
    )

    nodes = controller._fetch_products(None)

    assert [n.id for n in nodes] == ["shot010"]
    # Parent tracking still happens for folders outside the scope too,
    # so ancestor lookups keep working for folders reached later.
    assert controller._folder_parent_ids == {
        "shot010": None,
        "shot020": None,
    }


def test_fetch_products_returns_everything_without_scope(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"

    monkeypatch.setattr(
        "ayon_api.get_folders",
        lambda project_name, parent_ids, fields: [
            {"id": "shot010", "name": "shot010", "parentId": None},
        ],
    )

    nodes = controller._fetch_products(None)

    assert [n.id for n in nodes] == ["shot010"]


# ---------------------------------------------------------------------
# BrowserTasksWidget scope filtering
# ---------------------------------------------------------------------


def test_set_task_id_scope_filters_cached_rows_without_refetch(qtbot):
    widget = BrowserTasksWidget(Mock())
    qtbot.addWidget(widget)
    widget._last_task_items = [
        _task_item("task-1", "Animation"),
        _task_item("task-2", "Lighting"),
    ]
    widget._last_task_type_items = []
    widget._controller.get_task_sorting_mode.return_value = "name"

    widget.set_task_id_scope({"task-2"})

    names = [
        widget._model.index(row, 0).data(TASK_DATA_ROLE)["name"]
        for row in range(widget._model.rowCount())
    ]
    # No server round trip: the controller is never asked for tasks.
    widget._controller.get_task_items.assert_not_called()
    assert names == ["Lighting"]
    # "No task" isn't a real task id, so it can't be "mine".
    assert "No task" not in names


def test_set_task_id_scope_none_restores_no_task_row(qtbot):
    widget = BrowserTasksWidget(Mock())
    qtbot.addWidget(widget)
    widget._last_task_items = [_task_item("task-1", "Animation")]
    widget._last_task_type_items = []
    widget._controller.get_task_sorting_mode.return_value = "name"
    widget.set_task_id_scope({"task-1"})

    widget.set_task_id_scope(None)

    names = [
        widget._model.index(row, 0).data(TASK_DATA_ROLE)["name"]
        for row in range(widget._model.rowCount())
    ]
    assert names == ["Animation", "No task"]


# ---------------------------------------------------------------------
# SlicerFiltersMenu
# ---------------------------------------------------------------------


def test_slicer_filters_menu_offers_my_tasks_only_in_hierarchy(qtbot):
    menu = SlicerFiltersMenu()
    qtbot.addWidget(menu)

    menu.set_category(BrowserSlicerCategory.HIERARCHY)
    assert menu.isVisible()
    assert [i.key for i in menu._items] == [MY_TASKS_FILTER_KEY]

    menu.set_category(BrowserSlicerCategory.REVIEWS)
    assert not menu.isVisible()
    assert menu._items == []


def test_slicer_filters_menu_clears_selection_when_leaving_hierarchy(qtbot):
    menu = SlicerFiltersMenu()
    qtbot.addWidget(menu)
    menu.set_category(BrowserSlicerCategory.HIERARCHY)
    menu.set_filter_selected(MY_TASKS_FILTER_KEY, True)
    assert menu.get_selected_keys() == [MY_TASKS_FILTER_KEY]

    menu.set_category(BrowserSlicerCategory.REVIEWS)

    assert menu.get_selected_keys() == []
    assert MY_TASKS_FILTER_KEY not in menu._tags
