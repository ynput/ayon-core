"""Icon, name and actions of the edited placeholder."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.ui.components import AYContainer, AYLabel

from .placeholder_icons import get_placeholder_icon

# Space between the icon, name and actions of the edited placeholder
HEADER_SPACING = 10


class PlaceholderHeaderWidget(AYContainer):
    """Icon, name and actions of the edited placeholder.

    Actions are next to the name. They move to a row below the name when
    the name would not fit next to them.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.Grid,
            layout_spacing=HEADER_SPACING,
        )

        # Icon and title are separate labels, a label with both an icon
        #   and text may clip the last character of a bold text.
        icon_label = AYLabel(parent=self, icon="extension", icon_size=24)
        icon_label.set_icon(get_placeholder_icon(None))

        titles_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_spacing=0,
        )
        title_label = AYLabel(
            parent=titles_widget,
            rel_text_size=3,
            bold=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        subtitle_label = AYLabel(
            parent=titles_widget,
            dim=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        titles_widget.add_widget(title_label)
        titles_widget.add_widget(subtitle_label)

        actions_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        actions_widget.setVisible(False)

        layout = self.layout()
        layout.addWidget(icon_label, 0, 0, QtCore.Qt.AlignTop)
        layout.addWidget(titles_widget, 0, 1)
        layout.setColumnStretch(1, 1)

        self._icon_label = icon_label
        self._title_label = title_label
        self._subtitle_label = subtitle_label
        self._titles_widget = titles_widget
        self._actions_widget = actions_widget
        self._actions_below: Optional[bool] = None
        self._place_actions()

    def get_actions_widget(self) -> AYContainer:
        """Container of the placeholder action buttons.

        Returns:
            AYContainer: Container with horizontal layout.

        """
        return self._actions_widget

    def set_actions_visible(self, visible: bool) -> None:
        """Show the placeholder actions.

        Args:
            visible (bool): Actions are visible.

        """
        self._actions_widget.setVisible(visible)
        self._place_actions()

    def are_actions_below(self) -> bool:
        """Actions are on a row below the name.

        Returns:
            bool: Actions are below the name.

        """
        return bool(self._actions_below)

    def set_header(
        self, icon: Optional[QtGui.QIcon], title: str, subtitle: str
    ) -> None:
        """Show the placeholder.

        Args:
            icon (Optional[QtGui.QIcon]): Icon of the placeholder type.
            title (str): Name of the placeholder.
            subtitle (str): Text below the name.

        """
        if icon is not None:
            self._icon_label.set_icon(icon)
        self._title_label.setText(title)
        self._title_label.setToolTip(title)
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setToolTip(subtitle)
        self._place_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_actions()

    def _get_titles_width(self) -> int:
        """Width the name and subtitle need to be shown in full."""
        return max(
            label.fontMetrics().horizontalAdvance(label.text())
            for label in (self._title_label, self._subtitle_label)
        )

    def _place_actions(self) -> None:
        """Put actions next to the name, or below it when it doesn't fit."""
        actions_below = False
        if self._actions_widget.isVisibleTo(self):
            needed_width = (
                self._icon_label.sizeHint().width()
                + self._get_titles_width()
                + self._actions_widget.sizeHint().width()
                + (2 * HEADER_SPACING)
            )
            actions_below = needed_width > self.width()

        if actions_below == self._actions_below:
            return
        self._actions_below = actions_below

        layout = self.layout()
        layout.removeWidget(self._actions_widget)
        if actions_below:
            layout.addWidget(self._actions_widget, 1, 1, 1, 2)
        else:
            layout.addWidget(
                self._actions_widget, 0, 2, QtCore.Qt.AlignVCenter
            )
