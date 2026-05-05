"""View mode control: tool button opens an icon-only menu for the non-current layout."""
from __future__ import annotations

from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Qt

import qtawesome
from ayon_core.style import get_default_entity_icon_color

VIEW_MODE_LIST = "list"
VIEW_MODE_GRID = "grid"

_MODE_ICONS = (
    (VIEW_MODE_LIST, "fa.list"),
    (VIEW_MODE_GRID, "fa.th-large"),
)
_ICON_BY_MODE = dict(_MODE_ICONS)

_BUTTON_SIZE = 24
_BUTTON_WIDTH = _BUTTON_SIZE + 1
_ICON_SIZE = 17


class ViewModeSelector(QtWidgets.QToolButton):
    """Menu lists only the other layout (icon only). Stack index is synced via sync_from_stack_index."""

    view_mode_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ViewModeSelector")
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setIconSize(QtCore.QSize(_ICON_SIZE, _ICON_SIZE))
        self.setFixedSize(_BUTTON_WIDTH, _BUTTON_SIZE)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._current_mode = VIEW_MODE_LIST
        self._icon_color = get_default_entity_icon_color()

        self._menu = QtWidgets.QMenu(self)
        self._menu.setObjectName("ViewModeSelectorMenu")
        self._menu.setFixedSize(_BUTTON_WIDTH, _BUTTON_SIZE)
        self.setMenu(self._menu)
        self._switch_button = QtWidgets.QToolButton(self._menu)
        self._switch_button.setObjectName("ViewModeSelectorMenuButton")
        self._switch_button.setAutoRaise(True)
        self._switch_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._switch_button.setIconSize(QtCore.QSize(_ICON_SIZE, _ICON_SIZE))
        self._switch_button.setFixedSize(_BUTTON_WIDTH, _BUTTON_SIZE)
        self._switch_button.clicked.connect(self._on_switch_action)

        self._switch_action = QtWidgets.QWidgetAction(self)
        self._switch_action.setDefaultWidget(self._switch_button)
        self._menu.addAction(self._switch_action)

        self._sync_switch_action_and_button()

    def sync_from_stack_index(self, stack_index: int) -> None:
        """Align internal mode + button/menu with QStackedWidget index (no signal)."""
        mode = VIEW_MODE_GRID if stack_index == 1 else VIEW_MODE_LIST
        self._current_mode = mode
        self._sync_switch_action_and_button()

    def _alternate_mode(self) -> str:
        return (
            VIEW_MODE_GRID
            if self._current_mode == VIEW_MODE_LIST
            else VIEW_MODE_LIST
        )

    def _on_switch_action(self) -> None:
        self.set_view_mode(self._alternate_mode())
        self._menu.hide()

    def get_view_mode(self):
        return self._current_mode

    def set_view_mode(self, mode_id: str):
        if mode_id not in _ICON_BY_MODE:
            return
        if mode_id == self._current_mode:
            self._sync_switch_action_and_button()
            return
        self._current_mode = mode_id
        self._sync_switch_action_and_button()
        self.view_mode_changed.emit(mode_id)

    def _sync_switch_action_and_button(self) -> None:
        alt = self._alternate_mode()
        alt_label = "Grid" if alt == VIEW_MODE_GRID else "List"
        switch_tip = f"Switch to {alt_label} view"
        # Button icon shows the current mode (state indicator).
        # Dropdown item icon shows the alternate mode (the action available).
        self._switch_button.setIcon(
            qtawesome.icon(_ICON_BY_MODE[alt], color=self._icon_color)
        )
        self._switch_button.setToolTip(switch_tip)
        self.setIcon(
            qtawesome.icon(_ICON_BY_MODE[self._current_mode], color=self._icon_color)
        )
        self.setToolTip(switch_tip)
