"""Tests for AYSkeletonLoader visibility."""

from __future__ import annotations

from qtpy import QtGui, QtWidgets

from ayon_core.ui.components.tree_view import AYTreeView


def test_skeleton_hides_when_loading_ends_in_hidden_tab(qtbot) -> None:
    """Skeleton does not stay visible when loading ends while hidden.

    Loading takes longer than the skeleton show delay while the view is
    on an inactive tab, then finishes before the tab is opened.
    """
    tabs = QtWidgets.QTabWidget()
    qtbot.addWidget(tabs)
    view_tab = QtWidgets.QWidget()
    other_tab = QtWidgets.QWidget()
    view = AYTreeView(view_tab)
    view.set_loading_delay(0)
    model = QtGui.QStandardItemModel()
    view.setModel(model)
    QtWidgets.QVBoxLayout(view_tab).addWidget(view)
    tabs.addTab(view_tab, "View")
    tabs.addTab(other_tab, "Other")
    tabs.show()
    tabs.setCurrentWidget(other_tab)

    view.set_loading(True)
    skeleton = view._skeleton
    # Loading takes longer than the fade in
    qtbot.waitUntil(lambda: skeleton._opacity >= 1.0)

    model.appendRow(QtGui.QStandardItem("folder"))
    view.set_loading(False)
    qtbot.waitUntil(skeleton.isHidden, timeout=1000)

    tabs.setCurrentWidget(view_tab)
    assert not skeleton.isVisible()
