"""Visual regression tests for AYMenu.

Replicates the context menu built by
``ayon_core.ui.style._setup_context_menu`` and snapshots these states:

* ``00_initial``: host trigger button only.
* ``01_open_menu``: main menu open.
* ``02_open_submenu``: main menu + Sub-menu open, sub-menu row hovered.
* ``03_open_subsubmenu``: main menu + Sub-menu + Sub-sub-menu open,
  sub-sub-menu row hovered.
* ``04_hover_optional_action``: first AYOptionalAction in the main menu
  hovered.
"""

from __future__ import annotations

from ayon_core.ui.components import AYButton, AYMenu, AYOptionalAction
from ayon_core.ui.drawers import get_icon
from qtpy import QtCore, QtGui, QtWidgets
from utils.composite_widget import CompositeWidget
from widget_test import WidgetTest


def _icon(name: str) -> QtGui.QIcon:
    return get_icon(
        name, color="#f2f2f3", color_disabled="#727273", fill=False
    )


class MenuTest(WidgetTest):
    """Visual snapshots for AYMenu with nested submenus and optional rows."""

    size = (500, 350)
    tolerance = 0.0

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> QtWidgets.QWidget:
        """Build trigger button + nested AYMenu in a CompositeWidget."""
        self._menu = AYMenu()
        self._submenu = AYMenu("Sub-menu", parent=self._menu)
        self._subsub = AYMenu("Sub-sub-menu", parent=self._submenu)

        copy_icon = _icon("content_copy")
        one_icon = _icon("counter_1")
        two_icon = _icon("counter_2")
        pin_icon = _icon("pin")
        block_icon = _icon("block")
        danger_icon = _icon("delete")

        # text only
        self._menu.addAction("Text only")

        # icon + shortcut
        a2 = QtWidgets.QAction(copy_icon, "Icon + shortcut", parent=self._menu)
        a2.setShortcut("Ctrl+C")
        self._menu.addAction(a2)

        self._menu.addSeparator()

        # sub-menu with icon + radio-like sub-actions
        self._submenu.setIcon(pin_icon)
        self._submenu.addAction(one_icon, "Sub-action 1", "Ctrl+1")
        self._submenu.addAction(two_icon, "Sub-action 2", "Ctrl+2")
        self._subsub.addAction("Sub-sub-action 1")
        self._subsub.addAction("Sub-sub-action 2")
        self._subsub_action = self._submenu.addMenu(self._subsub)
        self._submenu_action = self._menu.addMenu(self._submenu)

        self._menu.addSeparator()

        # checkable action
        a4 = QtWidgets.QAction("Checkable action", self._menu)
        a4.setShortcut("Backspace")
        a4.setCheckable(True)
        self._menu.addAction(a4)

        self._menu.addSeparator()

        # optional actions
        self._opt_action = AYOptionalAction(
            "Optional action", parent=self._menu
        )
        self._menu.addAction(self._opt_action)

        opt2 = AYOptionalAction(
            "Optional action with icon",
            icon_name="save",
            parent=self._menu,
        )
        self._menu.addAction(opt2)

        opt3 = AYOptionalAction(
            "Optional action with icon disabled",
            icon_name="save",
            parent=self._menu,
        )
        opt3.setEnabled(False)
        self._menu.addAction(opt3)

        self._menu.addSeparator()

        # disabled action
        a6 = QtWidgets.QAction(block_icon, "Disabled action", self._menu)
        a6.setEnabled(False)
        self._menu.addAction(a6)

        # dangerous action
        a7 = QtWidgets.QAction(danger_icon, "Dangerous action", self._menu)
        a7.setShortcut("Ctrl+D")
        a7.setProperty("variant", "danger")
        self._menu.addAction(a7)

        # host trigger button
        self._trigger_btn = AYButton("Right-click target", fixed_width=True)
        self._root: CompositeWidget | None = None

        def _menu_pos() -> QtCore.QPoint:
            if self._root is None:
                return QtCore.QPoint(0, 0)
            return self._trigger_btn.mapTo(
                self._root,
                QtCore.QPoint(0, self._trigger_btn.height()),
            )

        def _submenu_pos() -> QtCore.QPoint:
            if self._root is None or not self._submenu.isVisible():
                return QtCore.QPoint(-10000, -10000)
            base = _menu_pos()
            rect = self._menu.actionGeometry(self._submenu_action)
            return QtCore.QPoint(
                base.x() + rect.right() + 2,
                base.y() + rect.top(),
            )

        def _subsub_pos() -> QtCore.QPoint:
            if self._root is None or not self._subsub.isVisible():
                return QtCore.QPoint(-10000, -10000)
            base = _submenu_pos()
            rect = self._submenu.actionGeometry(self._subsub_action)
            return QtCore.QPoint(
                base.x() + rect.right() + 2,
                base.y() + rect.top(),
            )

        root = CompositeWidget(
            widgets=[
                (self._menu, _menu_pos),
                (self._submenu, _submenu_pos),
                (self._subsub, _subsub_pos),
            ]
        )
        self._root = root

        layout = QtWidgets.QVBoxLayout(root)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.addWidget(self._trigger_btn, stretch=0)
        layout.addStretch(1)
        return root

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_menu(self) -> None:
        self._menu.show()
        QtWidgets.QApplication.processEvents()

    def _show_submenu(self) -> None:
        self._show_menu()
        self._menu.setActiveAction(self._submenu_action)
        self._submenu.show()
        QtWidgets.QApplication.processEvents()

    def _show_subsubmenu(self) -> None:
        self._show_submenu()
        self._submenu.setActiveAction(self._subsub_action)
        self._subsub.show()
        QtWidgets.QApplication.processEvents()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def open_menu(self) -> None:
        """Open the main menu with no rows highlighted."""
        self._show_menu()

    def open_submenu(self) -> None:
        """Open the Sub-menu by hovering its row in the main menu."""
        self._show_submenu()

    def open_subsubmenu(self) -> None:
        """Open the Sub-sub-menu by hovering its row in the Sub-menu."""
        self._show_subsubmenu()

    def hover_optional_action(self) -> None:
        """Hover the first AYOptionalAction row in the main menu."""
        assert self._qbot is not None
        self._show_menu()
        self._menu.setActiveAction(self._opt_action)
        QtWidgets.QApplication.processEvents()
        if self._opt_action.widget is not None:
            self._qbot.mouseMove(self._opt_action.widget)
        QtWidgets.QApplication.processEvents()

    def cleanup(self, step_name: str) -> None:
        """Hide all open menus and reset mouse position between steps."""
        self._subsub.hide()
        self._submenu.hide()
        self._menu.hide()
        QtWidgets.QApplication.processEvents()
        if self._qbot is not None and self._root is not None:
            self._qbot.mouseMove(self._root, QtCore.QPoint(0, 0))
        QtWidgets.QApplication.processEvents()

    def steps(self) -> list:
        return [
            self.open_menu,
            self.open_submenu,
            self.open_subsubmenu,
            self.hover_optional_action,
        ]
