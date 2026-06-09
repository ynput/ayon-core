"""Visual regression tests for OptionalAction and OptionalMenu.

Snapshots capture three states of an ``OptionalMenu`` containing actions
with and without option boxes:

  - ``00_initial``:          host button only (menu closed).
  - ``01_show_menu``:        menu open, no hover.
  - ``02_hover_action_body``: menu open, first action body highlighted.
  - ``03_hover_option_box``:  menu open, first action's option box highlighted.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets
from widget_test import WidgetTest

from ayon_core.ui.components.option_action import (
    OptionalAction,
)
from utils.composite_widget import CompositeWidget


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
        self._menu = QtWidgets.QMenu()

        self._action_with_option = OptionalAction(
            "Open File",
            icon_name="folder_open",
            use_option=True,
            parent=self._menu,
        )
        action_no_option = OptionalAction(
            "Export",
            icon_name=None,
            use_option=False,
            parent=self._menu,
        )
        action_with_option2 = OptionalAction(
            "Run Process",
            icon_name=None,
            use_option=True,
            parent=self._menu,
        )
        self._menu.addAction(self._action_with_option)
        self._menu.addAction(action_no_option)
        self._menu.addAction(action_with_option2)

        self._trigger_btn = QtWidgets.QPushButton("Open Menu")
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
        self._qbot.mouseMove(self._menu.actions()[0].widget)
        self._qbot.mouseMove(self._menu.actions()[0].widget.option)
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
