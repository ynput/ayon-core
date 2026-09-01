"""Visual regression tests for OptionalAction.

Snapshots capture three states of a ``QMenu`` containing actions
with and without option boxes:

  - ``00_initial``:          host button only (menu closed).
  - ``01_show_menu``:        menu open, no hover.
  - ``02_hover_action_body``: menu open, first action body highlighted.
  - ``03_hover_option_box``:  menu open, first action's option box highlighted.
"""

from __future__ import annotations

from ayon_core.ui.components import (
    AYButton,
    AYMenu,
    AYOptionalAction,
    AYOptionalMenu,
)
from qtpy import QtCore, QtWidgets
from utils.composite_widget import CompositeWidget
from widget_test import WidgetTest


class OptionalMenuTest(WidgetTest):
    """Visual snapshots for OptionalMenu with OptionalAction items.

    The widget under test is a ``CompositeWidget`` that composes the host
    trigger button and the floating ``OptionalMenu`` into a single image.
    """

    size = (380, 80)
    tolerance = 0.0

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> QtWidgets.QWidget:
        """Build the host widget and the menu, wrapped in a CompositeWidget.

        Returns:
            The root ``CompositeWidget`` for snapshot comparison.
        """
        self._menu = AYOptionalMenu()

        self._action_with_option = AYOptionalAction(
            "Open File",
            icon_name="folder_open",
            use_option=True,
            parent=self._menu,
        )
        action_no_option = AYOptionalAction(
            "Export",
            icon_name=None,
            use_option=False,
            parent=self._menu,
        )
        action_with_option2 = AYOptionalAction(
            "Run Process",
            icon_name=None,
            use_option=True,
            parent=self._menu,
        )
        self._menu.addAction(self._action_with_option)
        self._menu.addAction(action_no_option)
        self._menu.addAction(action_with_option2)

        self._trigger_btn = AYButton("Test Menu Options")
        self._root: CompositeWidget | None = None

        def _menu_pos() -> QtCore.QPoint:
            if self._root is None:
                return QtCore.QPoint(0, 0)
            return self._trigger_btn.mapTo(
                self._root,
                QtCore.QPoint(0, self._trigger_btn.height()),
            )

        root = CompositeWidget(widgets=[(self._menu, _menu_pos)])
        self._root = root

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.addWidget(self._trigger_btn)
        layout.addStretch(1)

        return root

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_menu(self) -> None:
        """Show the menu and flush events so action widgets are created."""
        self._menu.show()
        QtWidgets.QApplication.processEvents()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def show_menu(self) -> None:
        """Open the menu with no items highlighted."""
        self._open_menu()

    def hover_action_body(self) -> None:
        """Open the menu and highlight the first action's body."""
        assert self._qbot is not None
        self._open_menu()
        self._qbot.mouseMove(self._menu.actions()[0].widget)
        QtWidgets.QApplication.processEvents()

    def hover_option_box(self) -> None:
        """Open the menu and highlight the first action's option box."""
        assert self._qbot is not None
        self._open_menu()
        QtWidgets.QApplication.processEvents()
        widget = self._menu.actions()[0].widget
        self._qbot.mouseMove(widget, widget._option_rect().center())
        QtWidgets.QApplication.processEvents()

    def cleanup(self, step_name: str) -> None:
        """Hide the menu and clear hover state between steps.

        Args:
            step_name: Name of the completed step (unused).
        """
        self._menu.hide()
        QtWidgets.QApplication.processEvents()
        self._qbot.mouseMove(self._root, QtCore.QPoint(0, 0))
        QtWidgets.QApplication.processEvents()

    def steps(self) -> list:
        return [self.show_menu, self.hover_action_body, self.hover_option_box]


def test_optional_action_main_and_option_hit_regions(qtbot) -> None:
    menu = AYOptionalMenu()
    action = AYOptionalAction("Load", use_option=True, parent=menu)
    menu.addAction(action)
    qtbot.addWidget(menu)

    triggered = []
    optioned = []
    action.triggered.connect(lambda: triggered.append(True))
    action.option_clicked.connect(lambda: optioned.append(True))

    menu.popup(QtCore.QPoint(100, 100))
    qtbot.waitExposed(menu)
    widget = action.widget
    qtbot.mouseClick(
        widget,
        QtCore.Qt.MouseButton.LeftButton,
        pos=QtCore.QPoint(4, widget.height() // 2),
    )

    menu.popup(QtCore.QPoint(100, 100))
    qtbot.waitExposed(menu)
    widget = action.widget
    qtbot.mouseClick(
        widget,
        QtCore.Qt.MouseButton.LeftButton,
        pos=widget._option_rect().center(),
    )

    assert triggered == [True]
    assert optioned == [True]


def test_optional_menu_updates_explicit_hover_state(qtbot) -> None:
    menu = AYOptionalMenu()
    action = AYOptionalAction("Load", use_option=True, parent=menu)
    menu.addAction(action)
    qtbot.addWidget(menu)

    menu.popup(QtCore.QPoint(100, 100))
    qtbot.waitExposed(menu)
    menu.hovered.emit(action)

    assert action.widget._hovered is True


def test_optional_menu_inherits_application_style(qtbot, qapp) -> None:
    menu = AYOptionalMenu()
    qtbot.addWidget(menu)

    assert menu.style() is qapp.style()
    assert "paintEvent" not in AYOptionalMenu.__dict__
    assert AYOptionalMenu.paintEvent is AYMenu.paintEvent
