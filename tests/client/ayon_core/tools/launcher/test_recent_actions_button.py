"""Tests for the button of the recent actions in the launcher."""

from __future__ import annotations

import threading
import time
from typing import Optional

import pytest
from qtpy import QtCore, QtWidgets
from qtpy.QtTest import QTest

from ayon_core.tools.launcher.abstract import RecentActionItem
from ayon_core.tools.launcher.ui.recent_actions_widget import (
    RecentActionsButton,
    RecentActionsPopup,
)


class FakeController:
    """Just what the button asks of the launcher controller."""

    def __init__(self, supported: Optional[bool]) -> None:
        # What the server answers a load, 'None' if it is not reachable
        self.server_supported = supported
        self.supported: Optional[bool] = None
        self.loaded = False
        self.load_thread_ids: list[int] = []
        self.callbacks = {}
        self.items: list[RecentActionItem] = []

    def register_event_callback(self, topic, callback) -> None:
        self.callbacks[topic] = callback

    def refresh(self) -> None:
        self.callbacks["controller.refresh.finished"]()

    def is_recent_actions_supported(self) -> Optional[bool]:
        return self.supported

    def refresh_recent_action_items(self) -> None:
        self.load_thread_ids.append(threading.get_ident())
        self.supported = self.server_supported
        self.loaded = bool(self.server_supported)

    def get_recent_action_items(self) -> list[RecentActionItem]:
        return list(self.items)

    def are_recent_action_items_loaded(self) -> bool:
        return self.loaded


def wait_for_load(qapp, button: RecentActionsButton) -> None:
    end = time.time() + 5.0
    while button._load_thread is not None:
        if time.time() > end:
            raise AssertionError("Loading of the history did not finish.")
        qapp.processEvents()
        time.sleep(0.005)


@pytest.fixture
def parent(qapp):
    widget = QtWidgets.QWidget()
    yield widget
    widget.deleteLater()


def test_button_is_disabled_on_server_without_support(qapp, parent):
    controller = FakeController(supported=False)
    button = RecentActionsButton(controller, parent)
    # Usable until the server told otherwise
    assert button.isEnabled()

    controller.refresh()
    wait_for_load(qapp, button)

    assert not button.isEnabled()
    assert button.toolTip() == "Recent actions require AYON server 1.17.3+"
    # Loaded in a thread, never in the one of the UI
    assert controller.load_thread_ids
    assert threading.get_ident() not in controller.load_thread_ids


def test_button_stays_enabled_on_server_with_support(qapp, parent):
    controller = FakeController(supported=True)
    button = RecentActionsButton(controller, parent)

    controller.refresh()
    wait_for_load(qapp, button)
    controller.refresh()

    assert button.isEnabled()
    assert button.toolTip() == "Recent Actions"
    # Not loaded again once it was loaded, the popup loads it when opened
    assert button._load_thread is None
    assert len(controller.load_thread_ids) == 1


def test_button_stays_enabled_while_server_is_not_reachable(qapp, parent):
    controller = FakeController(supported=None)
    button = RecentActionsButton(controller, parent)

    controller.refresh()
    wait_for_load(qapp, button)

    assert button.isEnabled()
    assert button.toolTip() == "Recent Actions"


def test_button_created_after_the_check_uses_its_result(qapp, parent):
    controller = FakeController(supported=False)
    controller.supported = False

    button = RecentActionsButton(controller, parent)

    assert not button.isEnabled()


def test_popup_tells_the_server_is_not_supported(qapp, parent):
    controller = FakeController(supported=False)
    controller.supported = False
    popup = RecentActionsPopup(controller, parent)

    popup._rebuild_rows([])

    assert popup._empty_label.text() == (
        "Recent actions require AYON server 1.17.3+"
    )


def test_recent_action_runs_after_the_click_on_its_row(qapp, parent):
    controller = FakeController(supported=True)
    controller.items = [RecentActionItem(
        record_id="r1",
        action_type="local",
        identifier="maya",
        timestamp=time.time(),
        label="Maya",
    )]
    popup = RecentActionsPopup(controller, parent)
    popup.show()
    popup._rebuild_rows(controller.get_recent_action_items())
    (row,) = popup._rows
    triggered = []

    def trigger_recent_action(record_id):
        # The action shows a dialog, the history finishes loading
        #   meanwhile and the rows are rebuilt.
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(
            0,
            lambda: popup._rebuild_rows(controller.get_recent_action_items())
        )
        QtCore.QTimer.singleShot(50, loop.quit)
        loop.exec_()
        triggered.append(record_id)

    controller.trigger_recent_action = trigger_recent_action

    QTest.mouseClick(row, QtCore.Qt.LeftButton)
    end = time.time() + 5.0
    while not triggered and time.time() < end:
        qapp.processEvents()
        time.sleep(0.005)

    assert triggered == ["r1"]
    assert not popup.isVisible()
