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
from .layouts import AYVBoxLayout
from .line_edit import AYLineEdit
from .scroll_area import AYScrollArea
from .style_mixin import StyleMixin
from .container import AYContainer

log = logging.getLogger(__name__)


class _ItemRow(AYContainer):
    """Clickable row displaying an item label in the dropdown.

    Emits :attr:`clicked` with the item's key when pressed.

    Signals:
        clicked: Emitted with the item key on mouse press.
    """

    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent=parent,
            layout=AYContainer.Layout.HBox,
            layout_spacing=8,
            layout_margin=4,
            variant=AYFrame.Variants.Low,
        )

        self._key = key
        self._label_text = label

        self._label = AYLabel(label, parent=self)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self.add_widget(self._label, stretch=1)

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

    def add_custom_widget(self, widget: QWidget, stretch: int = 0) -> None:
        """Add a custom widget to the row layout.

        Args:
            widget: The widget to add.
            stretch: Layout stretch factor (default 0).
        """
        self.add_widget(widget, stretch=stretch)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.underMouse():
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(255, 255, 255, 20))
            painter.end()

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

    This component is designed to be generic and extensible. Applications can
    customize row rendering with :meth:`set_items_with_builder` or access
    existing rows through :meth:`get_rows`.

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

    def get_rows(self) -> list[tuple[str, str, "QWidget"]]:
        """Return the list of all item rows.

        Returns:
            List of (key, label, row_widget) tuples for custom widget manipulation.
        """
        return self._dropdown.all_items

    def set_items_with_builder(
        self,
        items: list[dict[str, str] | str],
        row_builder=None,
    ) -> None:
        """Set items and optionally apply a custom row builder function.

        This method provides a convenient way to customize row rendering
        without manually calling :meth:`get_rows` and iterating.

        Args:
            items: A list of dicts with ``key`` and ``label`` keys, or
                plain strings (used as both key and label).
            row_builder: Optional callable that receives (row, entry) and
                adds custom widgets to the row. Called for each item that
                has metadata beyond basic key/label.

        Example::

            def customize_row(row, entry):
                if "extra_data" in entry:
                    label = AYLabel(entry["extra_data"], dim=True)
                    row.add_custom_widget(label)

            items = [
                {"key": "k1", "label": "Item 1", "extra_data": "Extra"},
                {"key": "k2", "label": "Item 2", "extra_data": "More"},
            ]
            combo.set_items_with_builder(items, row_builder=customize_row)
        """
        # Set items normally
        self.set_items(items)

        # Apply custom builder if provided
        if row_builder is None:
            return

        # Create a dict mapping keys to items for quick lookup
        items_by_key = {
            item["key"]: item for item in items if isinstance(item, dict)
        }

        # Apply builder to rows that have metadata
        for key, label, row in self.get_rows():
            if key in items_by_key:
                row_builder(row, items_by_key[key])

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
