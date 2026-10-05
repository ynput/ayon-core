"""Compact tab bar to switch between pages of a narrow side panel."""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from ..style_types import get_ayon_style_data
from .buttons import AYButton
from .container import AYContainer


class AYTabBar(AYContainer):
    """Row of text tabs with an underline below the current one.

    The bar only tracks which tab is current, switching the actual content
    is left to the owner, e.g. by connecting :attr:`current_changed` to
    ``QStackedWidget.setCurrentIndex``.

    Args:
        labels: Tab labels, in display order.
        *args: Forwarded to ``AYContainer``.
        **kwargs: Forwarded to ``AYContainer``.

    Signals:
        current_changed (int): Index of the newly selected tab.
    """

    current_changed = QtCore.Signal(int)

    def __init__(self, labels: list[str], *args, **kwargs) -> None:
        kwargs.setdefault("variant", AYContainer.Variants.Low)
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            layout_spacing=4,
            **kwargs,
        )
        self._layout.setContentsMargins(0, 0, 0, 3)
        self._buttons: list[AYButton] = []
        self._current = 0
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        for idx, label in enumerate(labels):
            btn = AYButton(
                label,
                variant=AYButton.Variants.Nav,
                checkable=True,
                parent=self,
            )
            btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            self._group.addButton(btn, idx)
            self._buttons.append(btn)
            self.add_widget(btn)
        self.addStretch(1)
        if self._buttons:
            self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self.set_current)

        accent = get_ayon_style_data("QPushButton", "filled").get(
            "background-color", "#8fceff"
        )
        self._accent_color = QtGui.QColor(accent)
        self._line_color = QtGui.QColor(255, 255, 255, 24)

    def current(self) -> int:
        """Return index of the current tab."""
        return self._current

    def set_current(self, index: int) -> None:
        """Change the current tab.

        Args:
            index: Index of the tab to select.
        """
        if not 0 <= index < len(self._buttons):
            return
        self._buttons[index].setChecked(True)
        self.update()
        if index == self._current:
            return
        self._current = index
        self.current_changed.emit(index)

    def set_label(self, index: int, label: str) -> None:
        """Change label of a tab, e.g. to show an item count.

        Args:
            index: Index of the tab.
            label: New label.
        """
        if 0 <= index < len(self._buttons):
            self._buttons[index].setText(label)
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        bottom = self.height() - 1
        painter.fillRect(0, bottom, self.width(), 1, self._line_color)
        if self._buttons:
            geo = self._buttons[self._current].geometry()
            painter.fillRect(
                geo.left(), bottom - 1, geo.width(), 2, self._accent_color
            )
        painter.end()
