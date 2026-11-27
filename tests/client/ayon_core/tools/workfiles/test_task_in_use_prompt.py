"""Test task in-use prompt of the Workfiles tool."""
from __future__ import annotations

from unittest import mock

import pytest

pytest.importorskip("pytestqt")

from qtpy import QtWidgets  # noqa: E402

from ayon_core.pipeline.workfile.task_usage import (  # noqa: E402
    TaskUsageItem,
)
from ayon_core.tools.workfiles.widgets import utils  # noqa: E402
from ayon_core.tools.workfiles.widgets.utils import (  # noqa: E402
    confirm_task_in_use,
)

_SESSION = {
    "session_id": "other-user",
    "username": "artist2",
    "machine": "machine",
    "host_name": "maya",
    "workfile": "sh010_anim_v001.ma",
    "opened_at": "2026-01-01T12:00:00+00:00",
    "updated_at": "2026-01-01T12:00:00+00:00",
}


def _click_button(dialog, label):
    """Click a button of the dialog instead of the user."""
    for button in dialog.findChildren(QtWidgets.QAbstractButton):
        if button.text() == label and not button.isHidden():
            button.click()
            return dialog.result()
    dialog.reject()
    return dialog.result()


@pytest.fixture
def clicked_button(qtbot, monkeypatch):
    """Label of button that is clicked when the dialog is executed."""
    label = ["Continue anyway"]
    monkeypatch.setattr(
        QtWidgets.QDialog,
        "exec_",
        lambda dialog: _click_button(dialog, label[0]),
    )
    return label


@pytest.mark.parametrize(
    "button, expected",
    [
        ("Continue anyway", True),
        ("Cancel", False),
    ]
)
def test_confirm_task_in_use(clicked_button, qtbot, button, expected):
    """Prompt of the Workfiles tool and its workfile actions."""
    clicked_button[0] = button
    item = TaskUsageItem(**_SESSION)
    controller = mock.Mock()
    controller.get_task_usage_items.return_value = [item]
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)

    answer = confirm_task_in_use(controller, "task-1", parent)
    assert answer is expected
    controller.get_task_usage_items.assert_called_once_with("task-1")
    # Only confirmed sessions are not asked about again
    if expected:
        controller.confirm_task_usage_items.assert_called_once_with([item])
    else:
        controller.confirm_task_usage_items.assert_not_called()


def test_confirm_task_not_in_use(qtbot):
    controller = mock.Mock()
    controller.get_task_usage_items.return_value = []
    with mock.patch.object(utils, "TaskInUseDialog") as dialog_mock:
        assert confirm_task_in_use(controller, "task-1", None) is True
    dialog_mock.assert_not_called()
    controller.confirm_task_usage_items.assert_not_called()


def _increment_controller(selected_path: str, action_identifiers: list[str]):
    controller = mock.Mock()
    controller.get_task_usage_items.return_value = [
        TaskUsageItem(**_SESSION)
    ]
    selection = mock.Mock(filepath=selected_path)
    controller.get_workfile_action_selection.return_value = selection
    controller.get_workfile_action_items.return_value = [
        mock.Mock(identifier=identifier)
        for identifier in action_identifiers
    ]
    return controller, selection


def test_confirm_task_in_use_increment_and_open(clicked_button, qtbot):
    """Other user has opened the workfile that is about to be opened."""
    clicked_button[0] = "Increment and open"
    workfile = "/work/sh010_anim_v001.ma"
    controller, selection = _increment_controller(
        workfile, [utils.INCREMENT_AND_OPEN_IDENTIFIER]
    )

    assert confirm_task_in_use(
        controller, "task-1", None, workfile=workfile
    ) is False
    controller.confirm_task_usage_items.assert_called_once()
    controller.trigger_workfile_action.assert_called_once_with(
        utils.INCREMENT_AND_OPEN_IDENTIFIER, selection, None, {}
    )


@pytest.mark.parametrize(
    "workfile, selected_path, action_identifiers",
    [
        # Other user has opened a different workfile
        (
            "/work/sh010_anim_v002.ma",
            "/work/sh010_anim_v002.ma",
            ["core.increment-and-open"],
        ),
        # Opened workfile is not the selected workfile, e.g. browsed file
        (
            "/other/sh010_anim_v001.ma",
            "/work/sh010_anim_v002.ma",
            ["core.increment-and-open"],
        ),
        # The action is disabled
        ("/work/sh010_anim_v001.ma", "/work/sh010_anim_v001.ma", []),
    ]
)
def test_confirm_task_in_use_without_increment(
    clicked_button, qtbot, workfile, selected_path, action_identifiers
):
    clicked_button[0] = "Increment and open"
    controller, _ = _increment_controller(selected_path, action_identifiers)

    # The button is not available, the dialog is rejected
    assert confirm_task_in_use(
        controller, "task-1", None, workfile=workfile
    ) is False
    controller.confirm_task_usage_items.assert_not_called()
    controller.trigger_workfile_action.assert_not_called()

    clicked_button[0] = "Continue anyway"
    assert confirm_task_in_use(
        controller, "task-1", None, workfile=workfile
    ) is True
    controller.trigger_workfile_action.assert_not_called()
