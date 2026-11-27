"""Button that starts creation of a placeholder."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYButton, AYMenu

from ..abstract import PlaceholderPluginItem
from .placeholder_icons import CREATE_ICON, get_placeholder_icon


class AddPlaceholderButton(AYButton):
    """Button that starts creation of a placeholder.

    The placeholder type is picked from a menu when the host has more than
    one placeholder plugin, otherwise the only type is used right away.

    The button can be highlighted when adding a placeholder is the only
    thing to do, e.g. while the scene has none.

    Signals:
        create_requested: Create placeholder of plugin identifier (str).

    Args:
        text (str): Text of the button.
        parent (Optional[QtWidgets.QWidget]): Parent widget.
        variant (AYButton.Variants): Look of the button.

    """
    create_requested = QtCore.Signal(str)

    def __init__(
        self,
        text: str,
        parent: Optional[QtWidgets.QWidget] = None,
        variant: AYButton.Variants = AYButton.Variants.Surface,
    ):
        super().__init__(
            text,
            parent=parent,
            variant=variant,
            icon=CREATE_ICON,
            tooltip="Create a new placeholder",
        )
        self._default_variant = variant
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._highlighted = False
        self.setEnabled(False)
        self.clicked.connect(self._on_click)

    def set_plugin_items(
        self, plugin_items: list[PlaceholderPluginItem]
    ) -> None:
        """Set placeholder types that can be created.

        Args:
            plugin_items (list[PlaceholderPluginItem]): Available plugins.

        """
        self._plugin_items = list(plugin_items)
        self.setEnabled(bool(self._plugin_items))
        self._update_variant()

    def set_highlighted(self, highlighted: bool) -> None:
        """Show the button as the main action.

        Args:
            highlighted (bool): Use the filled look. Only applied when there
                is a placeholder type to create.

        """
        self._highlighted = highlighted
        self._update_variant()

    def is_highlighted(self) -> bool:
        """Button is shown as the main action.

        Returns:
            bool: Button uses the filled look.

        """
        return self._highlighted and bool(self._plugin_items)

    def _update_variant(self) -> None:
        if self.is_highlighted():
            self.set_variant(AYButton.Variants.Filled)
        else:
            self.set_variant(self._default_variant)

    def _on_click(self) -> None:
        if not self._plugin_items:
            return

        if len(self._plugin_items) == 1:
            self.create_requested.emit(self._plugin_items[0].identifier)
            return

        menu = AYMenu(self)
        for plugin_item in self._plugin_items:
            action = menu.addAction(plugin_item.label)
            action.setData(plugin_item.identifier)
            icon = get_placeholder_icon(plugin_item.icon)
            if icon is not None:
                action.setIcon(icon)

        action = menu.exec_(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        if action is not None:
            self.create_requested.emit(action.data())
