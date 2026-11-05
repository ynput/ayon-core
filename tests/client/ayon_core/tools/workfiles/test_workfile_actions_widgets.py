"""Tests of workfile actions widgets in workfiles tool."""
from __future__ import annotations

import collections
import dataclasses
from unittest import mock

from qtpy import QtCore, QtWidgets

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileActionResult,
    WorkfileActionSaveAsDialog,
)
from ayon_core.pipeline.actions.workfile import SAVE_AS_FORM_KEY
from ayon_core.tools.workfiles.abstract import (
    ActionItem,
    ActionSelectionData,
)
from ayon_core.tools.workfiles.widgets.actions_widgets import (
    WorkfileActionsRow,
    add_actions_to_menu,
)
from ayon_core.tools.workfiles.widgets.window import WorkfilesToolWindow


def _create_items(count: int) -> list[ActionItem]:
    return [
        ActionItem(
            label=f"Action {idx}",
            order=idx,
            icon=MaterialSymbolsIcon("folder_open"),
            tooltip=f"Tooltip {idx}",
            identifier=f"test.action-{idx}",
            data={"idx": idx},
        )
        for idx in range(count)
    ]


class _FakeController:
    def __init__(self, items: list[ActionItem]) -> None:
        self.items = items
        self.selection = ActionSelectionData(
            published=False,
            folder_id="folder-1",
            task_id="task-1",
            filepath="/work/file_v001.ma",
            rootless_path="{root[work]}/file_v001.ma",
        )
        self.triggered = []
        self.collect_count = 0
        self._callbacks = collections.defaultdict(list)

    def register_event_callback(self, topic, callback):
        self._callbacks[topic].append(callback)

    def emit(self, topic):
        for callback in self._callbacks[topic]:
            callback()

    def get_workfile_action_selection(self, published, with_workfile=True):
        selection = dataclasses.replace(self.selection, published=published)
        if not with_workfile:
            selection = dataclasses.replace(
                selection, filepath=None, rootless_path=None
            )
        return selection

    def get_workfile_action_items(self, selection):
        self.collect_count += 1
        return list(self.items)

    def trigger_workfile_action(
        self, identifier, selection, data, form_values
    ):
        self.triggered.append((identifier, selection, data, form_values))


def _is_faded_in(row) -> bool:
    return bool(row._buttons) and not row._opacity_effect.isEnabled()


def _create_row(qtbot, controller, width=400):
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    layout = QtWidgets.QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    row = WorkfileActionsRow(controller, parent)
    layout.addWidget(row)
    layout.addStretch(1)
    parent.resize(width, 200)
    parent.show()
    return parent, row


def test_row_collects_items_once_for_related_changes(qtbot):
    controller = _FakeController(_create_items(2))
    _parent, row = _create_row(qtbot, controller)

    # Change of task does select a workfile at the same time
    controller.emit("selection.task.changed")
    controller.emit("selection.workarea.changed")
    assert controller.collect_count == 0
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)
    assert controller.collect_count == 1

    # Available actions are collected again after an action
    controller.emit("workfile_action.finished")
    qtbot.waitUntil(lambda: controller.collect_count == 2, timeout=5000)


def test_row_shows_buttons_and_triggers_action(qtbot):
    controller = _FakeController(_create_items(2))
    _parent, row = _create_row(qtbot, controller)
    # Space of the row is reserved even if actions are not known yet
    assert row.isVisible()
    assert row.height() > 0
    assert not row._buttons
    height = row.height()

    controller.emit("selection.workarea.changed")
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)
    assert row.height() == height

    buttons = row._buttons
    assert len(buttons) == 2
    assert all(button.isVisible() for button in buttons)
    assert not row._more_btn.isVisible()
    assert "Action 0" in buttons[0].toolTip()
    assert "Tooltip 0" in buttons[0].toolTip()

    qtbot.mouseClick(buttons[1], QtCore.Qt.LeftButton)
    assert controller.triggered == [
        ("test.action-1", controller.selection, {"idx": 1}, {})
    ]


def test_row_hides_actions_that_do_not_fit(qtbot):
    controller = _FakeController(_create_items(12))
    parent, row = _create_row(qtbot, controller, width=150)

    controller.emit("selection.workarea.changed")
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)

    visible_buttons = [
        button for button in row._buttons if button.isVisible()
    ]
    assert 0 < len(visible_buttons) < 12
    assert row._more_btn.isVisible()
    assert len(row._overflow_items) == 12 - len(visible_buttons)
    # More button is the last one and still fits to the row
    more_geo = row._more_btn.geometry()
    assert more_geo.left() > visible_buttons[-1].geometry().right()
    assert more_geo.right() < row.width()

    parent.resize(1000, 200)
    qtbot.waitUntil(lambda: not row._more_btn.isVisible(), timeout=5000)
    assert all(button.isVisible() for button in row._buttons)


def test_row_shows_only_quick_actions(qtbot):
    items = _create_items(3)
    items[1].quick_action = False
    controller = _FakeController(items)
    _parent, row = _create_row(qtbot, controller)

    controller.emit("selection.workarea.changed")
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)

    assert len(row._buttons) == 2
    assert "Action 0" in row._buttons[0].toolTip()
    assert "Action 2" in row._buttons[1].toolTip()
    assert not row._more_btn.isVisible()
    # All actions are available for context menu
    assert controller.get_workfile_action_items(controller.selection) == items


def test_row_stays_steady_on_selection_change(qtbot):
    controller = _FakeController(_create_items(2))
    _parent, row = _create_row(qtbot, controller)

    controller.emit("selection.workarea.changed")
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)
    buttons = list(row._buttons)

    # Different workfile with the same actions
    first_selection = controller.selection
    controller.selection = dataclasses.replace(
        first_selection, filepath="/work/file_v002.ma"
    )
    controller.emit("selection.workarea.changed")
    # Buttons are not dimmed while actions are collected
    assert row._buttons == buttons
    assert all(button.isEnabled() for button in buttons)
    assert _is_faded_in(row)

    # Click before the actions are collected is related to new selection
    qtbot.mouseClick(buttons[0], QtCore.Qt.LeftButton)
    assert controller.triggered == [
        ("test.action-0", controller.selection, {"idx": 0}, {})
    ]
    # The same buttons are still used
    assert row._buttons == buttons
    assert _is_faded_in(row)

    # Action that is not available for the new selection is not triggered
    controller.triggered.clear()
    controller.items = controller.items[:1]
    controller.selection = dataclasses.replace(
        first_selection, filepath="/work/file_v003.ma"
    )
    controller.emit("selection.workarea.changed")
    qtbot.mouseClick(buttons[1], QtCore.Qt.LeftButton)
    assert controller.triggered == []
    assert len(row._buttons) == 1


def test_row_fades_out_without_actions(qtbot):
    controller = _FakeController(_create_items(1))
    _parent, row = _create_row(qtbot, controller)

    controller.emit("selection.workarea.changed")
    qtbot.waitUntil(lambda: _is_faded_in(row), timeout=5000)
    height = row.height()
    button = row._buttons[0]

    # Different selection without any actions
    controller.items = []
    controller.selection = dataclasses.replace(
        controller.selection, filepath=None, rootless_path=None
    )
    controller.emit("selection.workarea.changed")

    # Button that fades out cannot be triggered
    qtbot.mouseClick(button, QtCore.Qt.LeftButton)
    assert controller.triggered == []

    qtbot.waitUntil(lambda: not row._buttons, timeout=5000)
    assert not row._content_widget.isVisible()
    # Space of the row stays reserved
    assert row.isVisible()
    assert row.height() == height


def test_actions_menu_groups_items(qtbot):
    menu = QtWidgets.QMenu()
    qtbot.addWidget(menu)
    items = _create_items(3)
    items[1].group_label = "Group"
    items[2].group_label = "Group"

    items_by_action = add_actions_to_menu(menu, items)

    assert list(items_by_action.values()) == items
    top_actions = menu.actions()
    assert [action.text() for action in top_actions] == ["Action 0", "Group"]
    group_menu = top_actions[1].menu()
    assert [action.text() for action in group_menu.actions()] == [
        "Action 1", "Action 2"
    ]


def test_window_passes_save_as_values_to_action():
    selection = ActionSelectionData(
        published=False, folder_id="folder-1", task_id="task-1"
    )
    event = {
        "crashed": False,
        "identifier": "test.save-as",
        "selection": selection.to_data(),
        "data": {"key": "value"},
        "result": WorkfileActionResult(
            show_save_as_dialog=WorkfileActionSaveAsDialog(
                copied_from="/work/file_v001.ma"
            ),
        ),
    }
    values = {"filename": "file_v002.ma", "version": 2}
    window = mock.Mock()
    window._exec_save_as_dialog.return_value = values

    WorkfilesToolWindow._on_workfile_action_finished(window, event)

    window._exec_save_as_dialog.assert_called_once_with(
        WorkfileActionSaveAsDialog(copied_from="/work/file_v001.ma")
    )
    # The action continues with values of the dialog
    window._controller.trigger_workfile_action.assert_called_once_with(
        "test.save-as",
        selection,
        {"key": "value"},
        {SAVE_AS_FORM_KEY: values},
    )
    window._apply_action_result.assert_not_called()

    # Cancelled dialog does not trigger the action again
    window.reset_mock()
    window._exec_save_as_dialog.return_value = None
    WorkfilesToolWindow._on_workfile_action_finished(window, event)
    window._controller.trigger_workfile_action.assert_not_called()
    window._apply_action_result.assert_not_called()

    # Result without form or dialog is applied right away
    window.reset_mock()
    event["result"] = WorkfileActionResult(refresh=True)
    WorkfilesToolWindow._on_workfile_action_finished(window, event)
    window._controller.trigger_workfile_action.assert_not_called()
    window._apply_action_result.assert_called_once_with(event["result"])
