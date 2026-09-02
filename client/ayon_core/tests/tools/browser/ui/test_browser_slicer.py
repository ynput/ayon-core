from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

from qtpy import QtCore, QtGui, QtWidgets

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.ui._browser_slicer import BrowserSlicer
from ayon_core.tools.browser.ui.tasks_widget import (
    TASK_DATA_ROLE,
    BrowserTasksWidget,
)


def test_select_folder_chain_expands_selects_and_scrolls():
    parent_index = Mock()
    parent_index.isValid.return_value = True
    folder_index = Mock()
    folder_index.isValid.return_value = True
    selection_model = Mock()
    tree_view = Mock()
    tree_view.selectionModel.return_value = selection_model
    indexes = {
        "parent-id": parent_index,
        "folder-id": folder_index,
    }
    slicer = SimpleNamespace(
        _tree_view=tree_view,
        _get_view_index_by_id=indexes.__getitem__,
        _folder_selection_chain=["parent-id", "folder-id"],
        _folder_selection_attempt=0,
        _folder_selection_timer=Mock(),
    )

    BrowserSlicer._select_folder_chain(
        slicer,
        ["parent-id", "folder-id"],
        0,
    )

    tree_view.expand.assert_called_once_with(parent_index)
    selection_model.select.assert_called_once_with(
        folder_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )
    tree_view.setCurrentIndex.assert_called_once_with(folder_index)
    tree_view.scrollTo.assert_called_once_with(
        folder_index,
        QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
    )
    assert slicer._folder_selection_chain == []


def test_task_selection_aggregates_row_ids(qtbot):
    widget = BrowserTasksWidget(Mock())
    qtbot.addWidget(widget)
    rows = []
    for name, task_ids in (
        ("Animation", ["task-1", "task-2"]),
        ("Lighting", ["task-3"]),
    ):
        name_item = QtGui.QStandardItem(name)
        name_item.setData(
            {"name": name, "ids": task_ids},
            TASK_DATA_ROLE,
        )
        rows.append([name_item, QtGui.QStandardItem("")])
    widget._replace_rows(rows)

    selection_changed = Mock()
    widget.task_selection_changed.connect(selection_changed)
    selection = QtCore.QItemSelection()
    selection.select(
        widget._model.index(0, 0),
        widget._model.index(0, 1),
    )
    selection.select(
        widget._model.index(1, 0),
        widget._model.index(1, 1),
    )
    widget._view.selectionModel().select(
        selection,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )

    selection_changed.assert_called_once_with(
        ["Animation", "Lighting"],
        ["task-1", "task-2", "task-3"],
    )


def test_task_selection_updates_loader_controller():
    loader_controller = Mock()
    task_names_changed = Mock()
    slicer = SimpleNamespace(
        _loader_controller=loader_controller,
        task_names_changed=task_names_changed,
    )

    BrowserSlicer._on_task_selection_changed(
        slicer,
        ["Animation"],
        ["task-1", "task-2"],
    )

    loader_controller.set_selected_tasks.assert_called_once_with({
        "task-1",
        "task-2",
    })
    task_names_changed.emit.assert_called_once_with(["Animation"])
