"""Tests for the "My Tasks" slicer filter."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from qtpy import QtGui

from ayon_core.tools.browser.control import BrowserController
from ayon_core.tools.browser.ui._browser_slicer import SlicerCategories
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
from ayon_core.tools.browser.ui.tasks_widget import (
    TASK_DATA_ROLE,
    BrowserTasksWidget,
)
from ayon_core.tools.browser.ui.folders_model import (
    FOLDER_ID_ROLE,
    BrowserFoldersProxyModel,
)
from ayon_core.ui.components.table_filter import NO_VALUE


@pytest.fixture(autouse=True)
def _mock_addons_manager(monkeypatch):
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = []
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager",
        lambda: addon_manager,
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

    controller.set_my_tasks_filter(True)

    # Ancestors are not part of the scope - the folders proxy keeps
    # them visible through recursive filtering.
    assert controller.get_folder_id_scope() == {"shot010"}
    assert controller.get_task_id_scope() == {"task-1", "task-2"}


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


def _folders_proxy():
    """Proxy over 'episode > sequence > shot010' and a sibling 'shot020'."""
    model = QtGui.QStandardItemModel()
    items = {}
    for folder_id, parent_id in (
        ("episode", None),
        ("sequence", "episode"),
        ("shot010", "sequence"),
        ("shot020", "sequence"),
    ):
        item = QtGui.QStandardItem(folder_id)
        item.setData(folder_id, FOLDER_ID_ROLE)
        parent = items[parent_id] if parent_id else model.invisibleRootItem()
        parent.appendRow(item)
        items[folder_id] = item
    proxy = BrowserFoldersProxyModel()
    proxy.setSourceModel(model)
    return proxy


def _visible_folder_ids(proxy, parent=None):
    parent = parent or proxy.index(-1, -1)
    ids = []
    for row in range(proxy.rowCount(parent)):
        index = proxy.index(row, 0, parent)
        ids.append(index.data(FOLDER_ID_ROLE))
        ids.extend(_visible_folder_ids(proxy, index))
    return ids


def test_folders_proxy_scope_keeps_ancestors_of_scoped_folders(qtbot):
    proxy = _folders_proxy()

    proxy.set_folder_ids_filter({"shot010"})

    assert _visible_folder_ids(proxy) == ["episode", "sequence", "shot010"]


def test_folders_proxy_without_scope_shows_everything(qtbot):
    proxy = _folders_proxy()
    proxy.set_folder_ids_filter({"shot010"})

    proxy.set_folder_ids_filter(None)

    assert _visible_folder_ids(proxy) == [
        "episode", "sequence", "shot010", "shot020",
    ]


def test_folders_proxy_empty_scope_hides_everything(qtbot):
    proxy = _folders_proxy()

    proxy.set_folder_ids_filter(set())

    assert _visible_folder_ids(proxy) == []


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
    # The "No task" row isn't a real task id, so it can't be "mine".
    assert NO_VALUE not in names


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
    assert names == ["Animation", NO_VALUE]


# ---------------------------------------------------------------------
# SlicerCategories "My Tasks" toggle
# ---------------------------------------------------------------------


def _slicer_categories(qtbot, category=BrowserSlicerCategory.HIERARCHY):
    be_controller = Mock()
    be_controller.get_current_context.return_value = {}
    widget = SlicerCategories(category.value, Mock(), be_controller)
    qtbot.addWidget(widget)
    return widget


def test_my_tasks_toggle_visible_only_in_hierarchy(qtbot):
    widget = _slicer_categories(qtbot)
    btn = widget._my_tasks_btn
    assert btn.isVisibleTo(widget)

    widget.set_current_category(BrowserSlicerCategory.REVIEWS.value)
    assert not btn.isVisibleTo(widget)

    widget.set_current_category(BrowserSlicerCategory.HIERARCHY.value)
    assert btn.isVisibleTo(widget)


def test_my_tasks_toggle_has_artist_friendly_tooltip(qtbot):
    btn = _slicer_categories(qtbot)._my_tasks_btn

    assert "task" in btn.toolTip().lower()
    assert "you" in btn.toolTip().lower()


def test_my_tasks_toggle_unchecks_when_leaving_hierarchy(qtbot):
    widget = _slicer_categories(qtbot)
    widget._my_tasks_btn.setChecked(True)
    requested = Mock()
    widget.my_tasks_requested.connect(requested)

    widget.set_current_category(BrowserSlicerCategory.REVIEWS.value)

    assert not widget._my_tasks_btn.isChecked()
    requested.assert_called_once_with(False)


def test_my_tasks_toggle_emits_request(qtbot):
    widget = _slicer_categories(qtbot)
    requested = Mock()
    widget.my_tasks_requested.connect(requested)

    widget._my_tasks_btn.setChecked(True)

    requested.assert_called_once_with(True)


def test_set_current_category_updates_combo_before_emitting(qtbot):
    widget = _slicer_categories(qtbot)
    seen = []
    widget.category_changed.connect(
        lambda category: seen.append(
            (category, widget.current_category())
        )
    )

    widget.set_current_category(BrowserSlicerCategory.REVIEWS.value)

    reviews = BrowserSlicerCategory.REVIEWS.value
    assert seen == [(reviews, reviews)]


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
