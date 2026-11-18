"""Tests for AYSkeletonLoader visibility."""

from __future__ import annotations

import pytest
from qtpy import QtGui, QtWidgets

from ayon_core.ui.components.tree_view import AYTreeView


def _create_view(parent: QtWidgets.QWidget) -> AYTreeView:
    view = AYTreeView(parent)
    view.set_loading_delay(0)
    view.setModel(QtGui.QStandardItemModel(view))
    QtWidgets.QVBoxLayout(parent).addWidget(view)
    return view


def _inactive_tab(qtbot):
    """View is on a tab that is not active."""
    tabs = QtWidgets.QTabWidget()
    qtbot.addWidget(tabs)
    view_tab = QtWidgets.QWidget()
    other_tab = QtWidgets.QWidget()
    view = _create_view(view_tab)
    tabs.addTab(view_tab, "View")
    tabs.addTab(other_tab, "Other")
    tabs.show()
    tabs.setCurrentWidget(other_tab)
    return view, lambda: None, lambda: tabs.setCurrentWidget(view_tab)


def _closed_window(qtbot):
    """Tool window is closed and opened again later."""
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    view = _create_view(window)
    window.show()
    return view, window.hide, window.show


@pytest.mark.parametrize("setup", [_inactive_tab, _closed_window])
def test_skeleton_hides_when_loading_ends_while_hidden(qtbot, setup) -> None:
    """Skeleton does not stay visible when loading ends while hidden."""
    view, hide, show = setup(qtbot)

    view.set_loading(True)
    skeleton = view._skeleton
    # Loading takes longer than the fade in
    qtbot.waitUntil(lambda: skeleton._opacity >= 1.0)
    hide()

    view.model().appendRow(QtGui.QStandardItem("folder"))
    view.set_loading(False)
    qtbot.waitUntil(skeleton.isHidden, timeout=1000)

    show()
    assert not skeleton.isVisible()
