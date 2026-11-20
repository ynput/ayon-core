"""Tests for the button of the recent actions in the launcher."""

from __future__ import annotations

import threading
import time
from typing import Optional

import pytest
from qtpy import QtWidgets

from ayon_core.tools.launcher.ui.recent_actions_widget import (
    RecentActionsButton,
    RecentActionsPopup,
)


class FakeController:
    """Just what the button asks of the launcher controller."""

    def __init__(self, supported: bool) -> None:
        self.server_supported = supported
        self.supported: Optional[bool] = None
        self.check_thread_ids: list[int] = []
        self.callbacks = {}

    def register_event_callback(self, topic, callback) -> None:
        self.callbacks[topic] = callback

    def refresh(self) -> None:
        self.callbacks["controller.refresh.finished"]()

    def is_recent_actions_supported(self) -> Optional[bool]:
        return self.supported

    def check_recent_actions_support(self) -> bool:
        self.check_thread_ids.append(threading.get_ident())
        self.supported = self.server_supported
        return self.supported

    def get_recent_action_items(self) -> list:
        return []

    def are_recent_action_items_loaded(self) -> bool:
        return False


def wait_for_check(qapp, button: RecentActionsButton) -> None:
    end = time.time() + 5.0
    while button._support_thread is not None:
        if time.time() > end:
            raise AssertionError("Support check did not finish.")
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
    wait_for_check(qapp, button)

    assert not button.isEnabled()
    assert button.toolTip() == "Recent actions require AYON server 1.17.3+"
    # Asked in a thread, never in the one of the UI
    assert controller.check_thread_ids
    assert threading.get_ident() not in controller.check_thread_ids


def test_button_stays_enabled_on_server_with_support(qapp, parent):
    controller = FakeController(supported=True)
    button = RecentActionsButton(controller, parent)

    controller.refresh()
    wait_for_check(qapp, button)
    controller.refresh()

    assert button.isEnabled()
    assert button.toolTip() == "Recent Actions"
    # Not asked again once the server told
    assert button._support_thread is None
    assert len(controller.check_thread_ids) == 1


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
