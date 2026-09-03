"""Tests for the "My Tasks" slicer filter."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.control import BrowserController
from ayon_core.tools.browser.ui._browser_slicer_filters import (
    MyTasksToggleButton,
)
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
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
# BrowserController scope resolution
# ---------------------------------------------------------------------


def test_set_my_tasks_filter_resolves_folder_and_task_scope(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
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

    controller.set_my_tasks_filter(True)

    assert controller._folder_id_scope == {
        "episode", "sequence", "shot010",
    }
    assert controller.get_task_id_scope() == {"task-1", "task-2"}
    reset_calls.assert_called_once()


def test_set_my_tasks_filter_noop_when_unchanged(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    recompute = Mock(wraps=controller._recompute_my_tasks_scope)
    monkeypatch.setattr(
        controller, "_recompute_my_tasks_scope", recompute
    )

    controller.set_my_tasks_filter(False)

    recompute.assert_not_called()


def test_set_my_tasks_filter_clears_scope_when_disabled(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
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
    controller.set_my_tasks_filter(True)
    assert controller.get_task_id_scope() == {"task-1"}

    controller.set_my_tasks_filter(False)

    assert controller._folder_id_scope is None
    assert controller.get_task_id_scope() is None


def test_fetch_folders_restricts_to_folder_id_scope(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    controller._folder_id_scope = {"shot010"}

    monkeypatch.setattr(
        "ayon_api.get_folders",
        lambda project_name, parent_ids, fields: [
            {"id": "shot010", "name": "shot010", "parentId": None},
            {"id": "shot020", "name": "shot020", "parentId": None},
        ],
    )

    nodes = controller._fetch_folders(None)

    assert [n.id for n in nodes] == ["shot010"]
    # Parent tracking still happens for folders outside the scope too,
    # so ancestor lookups keep working for folders reached later.
    assert controller._folder_parent_ids == {
        "shot010": None,
        "shot020": None,
    }


def test_fetch_folders_returns_everything_without_scope(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"

    monkeypatch.setattr(
        "ayon_api.get_folders",
        lambda project_name, parent_ids, fields: [
            {"id": "shot010", "name": "shot010", "parentId": None},
        ],
    )

    nodes = controller._fetch_folders(None)

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
# MyTasksToggleButton
# ---------------------------------------------------------------------


def test_my_tasks_toggle_visible_only_in_hierarchy(qtbot):
    btn = MyTasksToggleButton()
    qtbot.addWidget(btn)

    btn.set_category(BrowserSlicerCategory.HIERARCHY)
    assert btn.isVisible()

    btn.set_category(BrowserSlicerCategory.REVIEWS)
    assert not btn.isVisible()


def test_my_tasks_toggle_has_artist_friendly_tooltip(qtbot):
    btn = MyTasksToggleButton()
    qtbot.addWidget(btn)

    assert "task" in btn.toolTip().lower()
    assert "you" in btn.toolTip().lower()


def test_my_tasks_toggle_unchecks_when_leaving_hierarchy(qtbot):
    btn = MyTasksToggleButton()
    qtbot.addWidget(btn)
    btn.set_category(BrowserSlicerCategory.HIERARCHY)
    changed = Mock()
    btn.toggled.connect(changed)
    btn.setChecked(True)
    changed.reset_mock()

    btn.set_category(BrowserSlicerCategory.REVIEWS)

    assert not btn.isChecked()
    changed.assert_called_once_with(False)


def test_my_tasks_toggle_emits_native_toggled_signal(qtbot):
    btn = MyTasksToggleButton()
    qtbot.addWidget(btn)
    btn.set_category(BrowserSlicerCategory.HIERARCHY)
    changed = Mock()
    btn.toggled.connect(changed)

    btn.setChecked(True)

    changed.assert_called_once_with(True)
    assert btn.isChecked()


# ---------------------------------------------------------------------
# Controller <-> toggle bidirectional sync (used by saved Views)
# ---------------------------------------------------------------------


def test_my_tasks_filter_enabled_property_reflects_state(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    monkeypatch.setattr(
        controller._loader_controller,
        "get_my_tasks_entity_ids",
        lambda project_name: {"folder_ids": set(), "task_ids": set()},
    )
    monkeypatch.setattr(controller, "get_folder_id_path", lambda fid: [])

    assert controller.my_tasks_filter_enabled is False

    controller.set_my_tasks_filter(True)

    assert controller.my_tasks_filter_enabled is True


def test_set_my_tasks_filter_emits_signal_only_on_change(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    monkeypatch.setattr(
        controller._loader_controller,
        "get_my_tasks_entity_ids",
        lambda project_name: {"folder_ids": set(), "task_ids": set()},
    )
    monkeypatch.setattr(controller, "get_folder_id_path", lambda fid: [])
    changed = Mock()
    controller.my_tasks_filter_changed.connect(changed)

    controller.set_my_tasks_filter(True)
    controller.set_my_tasks_filter(True)  # unchanged

    changed.assert_called_once_with(True)


# ---------------------------------------------------------------------
# BrowserTable view-extras wiring for the My Tasks filter
# ---------------------------------------------------------------------


def test_capture_view_extras_includes_my_tasks_filter():
    from ayon_core.tools.browser.ui._browser_table import BrowserTable

    table = SimpleNamespace(
        _controller=SimpleNamespace(
            my_tasks_filter_enabled=True,
            featured_version_order=["latest"],
            latest_per_folder=False,
            include_folder_children=False,
        ),
        _card_view=SimpleNamespace(card_width=200),
        _display_type=SimpleNamespace(display_type="table"),
    )

    extra = BrowserTable._capture_view_extras(table)

    assert extra["myTasksFilter"] is True


def test_apply_view_extras_forwards_my_tasks_filter_to_controller():
    from ayon_core.tools.browser.ui._browser_table import BrowserTable

    controller = Mock()
    table = SimpleNamespace(_controller=controller)

    BrowserTable._apply_view_extras(table, {"myTasksFilter": True})

    controller.set_my_tasks_filter.assert_called_once_with(True)
