"""Searchable combo-box component for the AYON UI Qt library.

Provides :class:`AYSearchableComboBox` — an :class:`AYLineEdit` that opens a
floating dropdown on click and on typing. The dropdown contains a scrollable
list of selectable items that are filtered in real-time as the user types.

The :class:`AYLineEdit` itself acts as the search input so there is no
duplicate search field inside the popup.

Typical usage::

    from ayon_core.ui.components.searchable_combo_box import (
        AYSearchableComboBox,
    )

    combo = AYSearchableComboBox(placeholder="Search items...")
    combo.set_items([
        {"key": "opt1", "label": "Option One"},
        {"key": "opt2", "label": "Option Two"},
    ])
    combo.item_selected.connect(on_selected)

Simple string list usage::

    combo = AYSearchableComboBox()
    combo.set_items(["Apple", "Banana", "Cherry"])
    combo.item_selected.connect(on_selected)
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor, QFocusEvent, QPainter, QPaintEvent, QShowEvent
from qtpy.QtWidgets import QApplication, QSizePolicy, QWidget

from ..style_types import get_ayon_style
from .dropdown import AYDropdownPopup
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYHBoxLayout, AYVBoxLayout
from .line_edit import AYLineEdit
from .scroll_area import AYScrollArea
from .style_mixin import StyleMixin

log = logging.getLogger(__name__)


class _ItemRow(QWidget):
    """Clickable row displaying an item label in the dropdown.

    Emits :attr:`clicked` with the item's key when pressed.

    Signals:
        clicked: Emitted with the item key on mouse press.
    """

    clicked = Signal(str)
    _HEIGHT = 32
    _HOVER_COLOR = QColor(255, 255, 255, 20)

    def __init__(
        self,
        key: str,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._key = key
        self._label_text = label
        self._hovered = False

        row_lyt = AYHBoxLayout(self, margin=4, spacing=8)

        self._label = AYLabel(label, parent=self)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        row_lyt.addWidget(self._label, 1)

        self.setFixedHeight(self._HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    @property
    def key(self) -> str:
        """Item key emitted on selection."""
        return self._key

    @property
    def label_text(self) -> str:
        """Display label used for filtering."""
        return self._label_text

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._hovered:
            painter = QPainter(self)
            painter.fillRect(self.rect(), self._HOVER_COLOR)
            painter.end()

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


class _SearchableDropdown(AYDropdownPopup):
    """Floating AYON-styled dropdown with a scrollable list of item rows.

    Filtering is applied externally via :meth:`filter_items`.

    Signals:
        item_selected: Emitted with the chosen item key.
    """

    item_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, variant=AYFrame.Variants.Low)

        scroll = AYScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = AYFrame(variant=AYFrame.Variants.Low)
        self._list_layout = AYVBoxLayout(
            self._list_widget, margin=0, spacing=0
        )
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._list_widget)

        outer = AYVBoxLayout(self, margin=4, spacing=0)
        outer.addWidget(scroll)

        self._scroll = scroll
        # (key, label, row_widget)
        self.all_items: list[tuple[str, str, _ItemRow]] = []

    def set_items(self, items: list[dict[str, str] | str]) -> None:
        """Rebuild the row list from *items*.

        Args:
            items: A list of dicts with ``key`` and ``label`` keys, or
                plain strings (used as both key and label).
        """
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.all_items.clear()

        for entry in items:
            if isinstance(entry, str):
                key = entry
                label = entry
            else:
                key = entry["key"]
                label = entry.get("label", key)

            row = _ItemRow(key, label, parent=self._list_widget)
            row.clicked.connect(self._on_item_clicked)
            self._list_layout.addWidget(row)
            self.all_items.append((key, label, row))

        self._list_layout.addStretch()

    def filter_items(self, text: str) -> None:
        """Show only rows whose key or label contains *text*.

        The comparison is case-insensitive.

        Args:
            text: Search string typed into the line edit.
        """
        needle = text.lower()
        for key, label, row in self.all_items:
            visible = not needle or (
                needle in key.lower() or needle in label.lower()
            )
            row.setVisible(visible)
        self._update_height()

    def _on_item_clicked(self, key: str) -> None:
        self.item_selected.emit(key)
        self.close()

    def _update_height(self) -> None:
        visible = sum(
            1 for _, _, row in self.all_items if row.isVisible()
        ) or 1
        h = min(visible * 40, 280)
        self.setFixedHeight(h)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_height()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        focus_widget = QApplication.focusWidget()
        if focus_widget and self.isAncestorOf(focus_widget):
            return
        self.close()
        super().focusOutEvent(event)


class AYSearchableComboBox(StyleMixin, QWidget):
    """AYON-styled line-edit that opens a searchable dropdown on click.

    The :class:`AYLineEdit` acts as the search input — typing filters the
    dropdown items in real-time with no second search field inside the popup.

    Signals:
        item_selected: Emitted with the chosen item key string.

    Args:
        placeholder: Hint text shown when the field is empty.
        parent: Optional parent widget.
    """

    item_selected = Signal(str)

    def __init__(
        self,
        placeholder: str = "Search...",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyle(get_ayon_style())

        self._line_edit = AYLineEdit(placeholder=placeholder, parent=self)
        layout = AYVBoxLayout(self, margin=0, spacing=0)
        layout.addWidget(self._line_edit)

        self._dropdown = _SearchableDropdown(parent=self)
        self._dropdown.item_selected.connect(self._on_item_selected)
        self._dropdown.hide()

        _orig_press = self._line_edit.mousePressEvent

        def _on_press(event):
            _orig_press(event)
            self._show_dropdown()

        self._line_edit.mousePressEvent = _on_press

        self._line_edit.textChanged.connect(self._on_text_changed)

    def set_items(self, items: list[dict[str, str] | str]) -> None:
        """Set the list of selectable items shown in the dropdown.

        Args:
            items: A list of dicts with ``key`` and ``label`` keys, or
                plain strings (used as both key and label).
        """
        self._dropdown.set_items(items)

    def clear(self) -> None:
        """Clear the line-edit and reset the dropdown filter."""
        self._line_edit.clear()
        self._dropdown.filter_items("")

    def _show_dropdown(self) -> None:
        if not self._dropdown.all_items:
            return
        self._dropdown.setFixedWidth(self.width())
        self._dropdown.show_below(self, y_offset=2)
        self._dropdown.raise_()

    def _on_text_changed(self, text: str) -> None:
        self._dropdown.filter_items(text)
        if not self._dropdown.isVisible():
            self._show_dropdown()

    def _on_item_selected(self, key: str) -> None:
        self._line_edit.clear()
        self._dropdown.filter_items("")
        self.item_selected.emit(key)
