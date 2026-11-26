"""Clicks on the tray menu must not trigger actions by accident.

Mouse events are sent directly to the menu, so Qt does not update its last
known cursor position. That is the same situation as a menu opened from
the tray icon, where Qt never saw the mouse move over the taskbar.
"""
from __future__ import annotations

import atexit
from unittest import mock

import pytest
from qtpy import QtCore, QtGui, QtWidgets

pytest.importorskip("aiohttp_middlewares")

from ayon_core.tools.tray.ui import tray as tray_module  # noqa: E402


@pytest.fixture
def tray_icon(qapp, monkeypatch):
    monkeypatch.setattr(tray_module, "TrayManager", mock.MagicMock())
    tray_icon = tray_module.SystemTrayIcon(QtWidgets.QMainWindow())
    yield tray_icon
    tray_icon.menu.hide()
    atexit.unregister(tray_icon.exit)


@pytest.fixture
def menu_actions(tray_icon):
    triggered = []
    actions = []
    for label in ("Launcher", "Browser", "Settings", "Exit"):
        action = tray_icon.menu.addAction(label)
        action.triggered.connect(
            lambda _=False, label=label: triggered.append(label)
        )
        actions.append(action)
    return actions, triggered


def _popup_with_cursor_on(menu, action):
    """Open the menu with the cursor above 'action'.

    Returns:
        QtCore.QPoint: Global cursor position.

    """
    menu_pos = QtCore.QPoint(100, 100)
    menu.ensurePolished()
    menu.adjustSize()
    cursor_pos = menu_pos + menu.actionGeometry(action).center()
    QtGui.QCursor.setPos(cursor_pos)
    if QtGui.QCursor.pos() != cursor_pos:
        pytest.skip("Cursor position can't be set on this platform")
    menu.popup(menu_pos)
    assert menu.isVisible()
    assert menu.actionAt(menu.mapFromGlobal(cursor_pos)) is action
    return cursor_pos


def _send_mouse(menu, event_type, global_pos, button, buttons):
    local_pos = QtCore.QPointF(menu.mapFromGlobal(global_pos))
    event = QtGui.QMouseEvent(
        event_type,
        local_pos,
        QtCore.QPointF(global_pos),
        button,
        buttons,
        QtCore.Qt.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(menu, event)


def _click(menu, global_pos):
    left = QtCore.Qt.LeftButton
    _send_mouse(menu, QtCore.QEvent.MouseButtonPress, global_pos, left, left)
    _send_mouse(
        menu,
        QtCore.QEvent.MouseButtonRelease,
        global_pos,
        left,
        QtCore.Qt.NoButton,
    )


def test_click_where_menu_opened_closes_menu(tray_icon, menu_actions):
    actions, triggered = menu_actions
    menu = tray_icon.menu
    cursor_pos = _popup_with_cursor_on(menu, actions[-1])

    _click(menu, cursor_pos)

    assert triggered == []
    assert not menu.isVisible()


def test_release_without_press_is_ignored(tray_icon, menu_actions):
    """Qt on Windows sends a release on the first mouse move after a window
    was closed with its title bar close button."""
    actions, triggered = menu_actions
    menu = tray_icon.menu
    cursor_pos = _popup_with_cursor_on(menu, actions[-1])

    left = QtCore.Qt.LeftButton
    no_button = QtCore.Qt.NoButton
    pos = cursor_pos + QtCore.QPoint(2, 1)
    _send_mouse(menu, QtCore.QEvent.MouseMove, pos, no_button, left)
    _send_mouse(menu, QtCore.QEvent.MouseButtonRelease, pos, left, no_button)

    assert triggered == []
    assert menu.isVisible()

    target = menu.mapToGlobal(menu.actionGeometry(actions[0]).center())
    _send_mouse(menu, QtCore.QEvent.MouseMove, target, no_button, no_button)
    _click(menu, target)

    assert triggered == ["Launcher"]


def test_click_after_moving_triggers_action(tray_icon, menu_actions):
    actions, triggered = menu_actions
    menu = tray_icon.menu
    _popup_with_cursor_on(menu, actions[-1])

    target = menu.mapToGlobal(menu.actionGeometry(actions[0]).center())
    _send_mouse(
        menu,
        QtCore.QEvent.MouseMove,
        target,
        QtCore.Qt.NoButton,
        QtCore.Qt.NoButton,
    )
    _click(menu, target)

    assert triggered == ["Launcher"]
