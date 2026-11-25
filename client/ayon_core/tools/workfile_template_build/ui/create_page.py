"""Publisher-like Create page for placeholder types."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYButton, AYContainer, AYLabel

from ..abstract import PlaceholderPluginItem
from .placeholder_icons import get_placeholder_icon


class CreatePage(AYContainer):
    """Choose the placeholder type to create in the open scene."""

    plugin_selected = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_margin=24,
            layout_spacing=8,
        )

        title = AYLabel("Create a placeholder", parent=self, rel_text_size=3)
        description = AYLabel(
            "Choose what the next placeholder should load or create.",
            parent=self,
            dim=True,
        )
        description.setWordWrap(True)

        plugins_widget = QtWidgets.QWidget(self)
        plugins_layout = QtWidgets.QVBoxLayout(plugins_widget)
        plugins_layout.setContentsMargins(0, 8, 0, 0)
        plugins_layout.setSpacing(6)
        plugins_layout.addStretch(1)

        empty_label = AYLabel(
            "No placeholder types are available in this host.",
            parent=self,
            dim=True,
        )
        empty_label.setVisible(False)

        self.add_widget(title)
        self.add_widget(description)
        self.add_widget(plugins_widget, stretch=1)
        self.add_widget(empty_label)

        self._plugins_widget = plugins_widget
        self._plugins_layout = plugins_layout
        self._empty_label = empty_label
        self._buttons: dict[str, AYButton] = {}

    def set_plugin_items(
        self, plugin_items: list[PlaceholderPluginItem]
    ) -> None:
        """Rebuild the list of available placeholder types."""
        while self._plugins_layout.count() > 1:
            item = self._plugins_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._buttons = {}
        for plugin_item in plugin_items:
            button = AYButton(
                plugin_item.label,
                parent=self._plugins_widget,
                variant=AYButton.Variants.Surface,
                icon=get_placeholder_icon(plugin_item.icon),
            )
            button.clicked.connect(
                lambda _checked=False, identifier=plugin_item.identifier: (
                    self.plugin_selected.emit(identifier)
                )
            )
            self._plugins_layout.insertWidget(
                self._plugins_layout.count() - 1, button
            )
            self._buttons[plugin_item.identifier] = button

        self._empty_label.setVisible(not plugin_items)
