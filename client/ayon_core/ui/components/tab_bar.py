"""Compact tab bar to switch between pages of a narrow side panel."""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from ..style_types import get_ayon_style_data
from .buttons import AYButton
from .container import AYContainer


class AYTabBar(AYContainer):
    """Row of tabs, laid out like the tabs of the web details panel.

    Tabs are added in display order with :meth:`add_tab`, and
    :meth:`add_stretch` pushes the tabs added after it to the right, e.g.
    the activity feed as an icon on the left and "Details" on the right::

        tabs = AYTabBar()
        tabs.add_tab("Activity", icon="forum", icon_only=True)
        tabs.add_stretch()
        details_index = tabs.add_tab("Details")
        tabs.set_current(details_index)

    The bar only tracks which tab is current, switching the actual content
    is left to the owner, e.g. by connecting :attr:`current_changed` to
    ``QStackedWidget.setCurrentIndex``. The first tab is current until
    :meth:`set_current` is called. A line below the tabs separates them
    from the content.

    Args:
        *args: Forwarded to ``AYContainer``.
        **kwargs: Forwarded to ``AYContainer``.

    Signals:
        current_changed (int): Index of the newly selected tab.
    """

    current_changed = QtCore.Signal(int)

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("variant", AYContainer.Variants.Low)
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            layout_spacing=4,
            **kwargs,
        )
        # Room for the line below the tabs
        self._layout.setContentsMargins(0, 0, 0, 6)
        # Same color as separators of menus
        self._line_color = QtGui.QColor(
            get_ayon_style_data("QMenu", "default").get(
                "separator-color", "#41474d"
            )
        )
        self._buttons: list[AYButton] = []
        self._current = 0
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.set_current)

    def add_tab(
        self,
        label: str,
        icon: str | None = None,
        icon_only: bool = False,
    ) -> int:
        """Add a tab at the end of the bar.

        Args:
            label: Label of the tab, its tooltip if it is icon only.
            icon: Material symbol shown before the label.
            icon_only: Show only the icon, to keep the bar narrow.

        Returns:
            Index of the tab.
        """
        index = len(self._buttons)
        btn = AYButton(
            "" if icon and icon_only else label,
            variant=AYButton.Variants.Nav,
            icon=icon,
            checkable=True,
            tooltip=label if icon and icon_only else "",
            parent=self,
        )
        btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        btn.setChecked(index == self._current)
        self._group.addButton(btn, index)
        self._buttons.append(btn)
        self.add_widget(btn)
        return index

    def add_stretch(self) -> None:
        """Push the tabs added after it to the right side of the bar."""
        self.addStretch(1)

    def current(self) -> int:
        """Return index of the current tab."""
        return self._current

    def button(self, index: int) -> AYButton:
        """Return the button of a tab.

        Args:
            index: Index of the tab.
        """
        return self._buttons[index]

    def set_current(self, index: int) -> None:
        """Change the current tab.

        Args:
            index: Index of the tab to select.
        """
        if not 0 <= index < len(self._buttons):
            return
        self._buttons[index].setChecked(True)
        if index == self._current:
            return
        self._current = index
        self.current_changed.emit(index)

    def set_label(self, index: int, label: str) -> None:
        """Change label of a tab, e.g. to show an item count.

        The label of an icon only tab is its tooltip.

        Args:
            index: Index of the tab.
            label: New label.
        """
        if not 0 <= index < len(self._buttons):
            return
        btn = self._buttons[index]
        if btn.toolTip():
            btn.setToolTip(label)
        else:
            btn.setText(label)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.fillRect(
            0, self.height() - 1, self.width(), 1, self._line_color
        )
        painter.end()
