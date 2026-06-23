"""AYFilter component for multi-select filtering with tags and dropdown.

This module provides:
- FilterItem: Data model for filter options
- FilterCheckboxDelegate: Custom delegate for checkbox-style rendering
- FilterDropdownPopup: Floating popup for filter selection
- AYFilter: Base filter widget with tag bar and dropdown toggle
- AYFilterByCategory: Subclass managing FilterItem data and checkbox popup
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from qtpy import QtCore, QtWidgets
from qtpy.QtCore import QModelIndex, QPersistentModelIndex, Qt, Signal
from qtpy.QtGui import QColor, QPainter, QMouseEvent
from qtpy.QtWidgets import QStyle, QStyleOptionViewItem

from ..style_types import get_ayon_style
from ..variants import QFrameVariants, QStyledItemDelegateVariants

from .buttons import AYButton
from .container import AYContainer
from .dropdown import AYDropdownPopup
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYVBoxLayout
from .tag import AYTag

logger = logging.getLogger(__name__)


@dataclass
class FilterItem:
    """Data model for a single filter option.

    Attributes:
        key: Unique identifier for the filter.
        label: Display text shown in dropdown and tags.
        selected: Current selection state.
        color: Optional background color for tag display.
        icon: Optional material icon name.
        enabled: Whether the filter can be toggled.
    """

    key: str
    label: str
    selected: bool = False
    color: str | None = field(default=None)
    icon: str | None = field(default=None)
    enabled: bool = True

    def __hash__(self) -> int:
        """Return hash based on key."""
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        """Compare equality based on key."""
        if isinstance(other, FilterItem):
            return self.key == other.key
        return False


class FilterCheckboxDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate for rendering filter items with checkbox indicators.

    Draws a small square checkbox indicator on the right side of each item.
    Checked items display an X icon inside the checkbox.

    Attributes:
        CHECKBOX_SIZE: Size of the checkbox indicator in pixels.
        CHECKBOX_MARGIN: Margin around the checkbox.
        TEXT_PADDING: Padding for the text from the left edge.
    """

    CHECKBOX_SIZE = 16
    CHECKBOX_MARGIN = 8
    TEXT_PADDING = 12

    Variants = QStyledItemDelegateVariants

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        variant: Variants = Variants.Default,
    ) -> None:
        """Initialize the delegate.

        Args:
            parent: Optional parent widget.
            variant: Style variant for the delegate.
        """
        super().__init__(parent)
        self._variant_str = variant.value

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the filter item with checkbox indicator.

        Args:
            painter: QPainter instance for rendering.
            option: Style options for the item.
            index: Model index of the item.
        """
        # Update option with model data for the drawer
        option.text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        option.checkState = (
            Qt.CheckState.Checked
            if check_state == Qt.CheckState.Checked
            else Qt.CheckState.Unchecked
        )

        # Delegate painting to AYONStyle
        parent = self.parent()
        widget = parent if isinstance(parent, QtWidgets.QWidget) else None
        get_ayon_style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            option,
            painter,
            widget,
        )

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QtCore.QSize:
        """Return size hint for the item.

        Args:
            option: Style options for the item.
            index: Model index of the item.

        Returns:
            Recommended size for the item.
        """
        base = super().sizeHint(option, index)
        return QtCore.QSize(base.width(), max(base.height(), 36))

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Handle click events to toggle checkbox state.

        Args:
            event: The input event.
            model: The data model.
            option: Style options for the item.
            index: Model index of the item.

        Returns:
            True if the event was handled.
        """
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            current = index.data(Qt.ItemDataRole.CheckStateRole)
            new_state = (
                Qt.CheckState.Unchecked
                if current == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)


class FilterDropdownPopup(AYDropdownPopup):
    """Floating popup widget for filter selection.

    This popup appears below the toggle button and contains a list of
    filter items with checkboxes. It closes when clicking outside,
    pressing Escape, or when explicitly closed.

    Signals:
        item_toggled: Emitted when a filter item is toggled.
                      Passes (key: str, selected: bool).
        popup_closed: Inherited from ``AYDropdownPopup``. Emitted when
            the popup is closed.
    """

    item_toggled = Signal(str, bool)  # (key, selected)

    # Styling constants
    POPUP_MIN_WIDTH = 180
    POPUP_MAX_HEIGHT = 300

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the dropdown popup.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent, variant=AYDropdownPopup.Variants.Low)

        self._init_ui()

    def _init_ui(self) -> None:
        """Build the popup layout."""
        layout = AYVBoxLayout(self, margin=4, spacing=0)

        # List widget for filter items
        self._list_widget = QtWidgets.QListWidget(self)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self._list_widget.setItemDelegate(
            FilterCheckboxDelegate(self._list_widget)
        )
        self._list_widget.setMouseTracking(True)
        self._list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list_widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self._list_widget.clicked.connect(self._on_item_clicked)

        layout.addWidget(self._list_widget)

        # Set size constraints
        self.setMinimumWidth(self.POPUP_MIN_WIDTH)
        self.setMaximumHeight(self.POPUP_MAX_HEIGHT)

    def populate(self, items: List[FilterItem]) -> None:
        """Populate the list with filter items.

        Args:
            items: List of FilterItem objects to display.
        """
        self._list_widget.clear()
        for item in items:
            self._add_list_item(item)

        # Adjust height based on content
        self._adjust_size()

    def _add_list_item(self, item: FilterItem) -> None:
        """Add a filter item to the list widget.

        Args:
            item: The FilterItem to add to the list.
        """
        list_item = QtWidgets.QListWidgetItem(item.label)
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item.key)
        list_item.setData(
            QtCore.Qt.ItemDataRole.CheckStateRole,
            QtCore.Qt.CheckState.Checked
            if item.selected
            else QtCore.Qt.CheckState.Unchecked,
        )
        list_item.setFlags(
            list_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        )
        self._list_widget.addItem(list_item)

    def _adjust_size(self) -> None:
        """Adjust popup size based on content."""
        item_count = self._list_widget.count()
        if item_count == 0:
            return

        # Calculate height based on items
        row_height = 36  # From delegate sizeHint
        content_height = item_count * row_height + 8  # 8 for margins
        height = min(content_height, self.POPUP_MAX_HEIGHT)
        self.setFixedHeight(height)

    def update_item_state(self, key: str, selected: bool) -> None:
        """Update the check state of a specific item.

        Args:
            key: Key of the item to update.
            selected: New selection state.
        """
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == key:
                item.setData(
                    QtCore.Qt.ItemDataRole.CheckStateRole,
                    QtCore.Qt.CheckState.Checked
                    if selected
                    else QtCore.Qt.CheckState.Unchecked,
                )
                break

    def _on_item_clicked(self, index: QtCore.QModelIndex) -> None:
        """Handle list item click - emit toggle signal.

        Args:
            index: Model index of the clicked item.
        """
        item = self._list_widget.item(index.row())
        if not item:
            return

        key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        current_state = item.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        new_selected = current_state == QtCore.Qt.CheckState.Checked

        self.item_toggled.emit(key, new_selected)


class AYFilter(AYFrame):
    """Base filter widget with tag bar and dropdown toggle.

    Provides the tag bar UI, toggle button, dropdown show/hide logic,
    and tag management. Subclasses supply a popup widget via
    ``_create_dropdown_popup()`` and handle tag removal via
    ``_handle_tag_removed()``.

    Signals:
        filter_changed: Emitted when selection changes. Passes list of
                        selected keys.
        filter_added: Emitted when a filter is selected. Passes the key.
        filter_removed: Emitted when a filter is deselected. Passes the key.
    """

    filter_changed = Signal(list)  # List[str] of selected keys
    filter_added = Signal(str)  # key of added filter
    filter_removed = Signal(str)  # key of removed filter

    Variants = QFrameVariants

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        label: str = "Sort by",
        default_color: str = "#8fceff",
        variant: Variants = Variants.Low,
    ) -> None:
        """Initialize the base filter widget.

        Args:
            parent: Optional parent widget.
            label: Text displayed before the filter tags.
            default_color: Default tag color when item has no color set.
            variant: Frame variant for background styling.
        """
        super().__init__(parent=parent, variant=variant, margin=0)

        self._label_text = label
        self._default_color = default_color
        self._tags: dict[str, AYTag] = {}
        self._dropdown_visible = False

        self._init_ui()
        self._connect_signals()

        self.setStyle(get_ayon_style())

    def set_label(self, text: str) -> None:
        """Set the label text.

        Args:
            text: New label text to display.
        """
        self._label_text = text
        self._label.setText(text)

    # --- Hooks for subclasses ---

    def _create_dropdown_popup(
        self,
    ) -> AYDropdownPopup | None:
        """Create and return the dropdown popup widget.

        Subclasses override this to return a concrete popup instance.
        The base implementation returns ``None`` (no popup).

        Returns:
            An ``AYDropdownPopup`` instance or ``None``.
        """
        return None

    def _handle_tag_removed(self, key: str) -> None:
        """React to a tag dismissal.

        Called when the user clicks the X on a tag. Subclasses override
        this to update their data model (e.g. call
        ``set_filter_selected(key, False)``).

        Args:
            key: Key of the dismissed tag.
        """

    def get_selected_keys(self) -> List[str]:
        """Return the list of selected filter keys.

        The base implementation returns an empty list. Subclasses that
        manage selection state must override this method.

        Returns:
            List of selected keys.
        """
        return []

    # --- UI Setup ---

    def _init_ui(self) -> None:
        """Build the widget layout."""
        main_layout = AYVBoxLayout(self, margin=0, spacing=0)

        # Top bar
        self._top_bar = AYContainer(
            parent=self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=4,
            layout_spacing=4,
        )
        main_layout.addWidget(self._top_bar)

        # Label
        self._label = AYLabel(self._label_text, parent=self)
        self._label.setContentsMargins(10, 0, 5, 0)
        self._top_bar.add_widget(self._label)

        # Tags container
        self._tags_container = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Default,
            layout_margin=0,
            layout_spacing=4,
        )
        lyt = self._tags_container.layout()
        if lyt:
            lyt.setSizeConstraint(
                QtWidgets.QLayout.SizeConstraint.SetFixedSize
            )
        self._top_bar.add_widget(self._tags_container)

        # Spacer
        self._top_bar.addStretch()

        # Toggle button
        self._toggle_btn = AYButton(
            icon="keyboard_arrow_down",
            variant=AYButton.Variants.Nav_Small,
            tooltip="Toggle filter options",
        )
        self._toggle_btn.setContentsMargins(4, 4, 4, 10)
        self._top_bar.add_widget(self._toggle_btn)

        # Create floating dropdown popup via hook (not added to layout)
        self._dropdown_popup = self._create_dropdown_popup()

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._toggle_btn.clicked.connect(self._on_toggle_dropdown)
        if self._dropdown_popup is not None:
            self._dropdown_popup.popup_closed.connect(self._on_popup_closed)

    # --- Tag management ---

    def _sync_tags_from_items(self, items: List[FilterItem]) -> None:
        """Synchronize tags with a list of filter items.

        Args:
            items: The current list of filter items.
        """
        for item in items:
            if item.selected and item.key not in self._tags:
                self._add_tag(item)
            elif not item.selected and item.key in self._tags:
                self._remove_tag(item.key)

    def _add_tag(self, item: FilterItem) -> None:
        """Create and add a tag widget for a filter item.

        Args:
            item: The FilterItem to create a tag for.
        """
        if item.key in self._tags:
            return

        color = QColor(item.color or self._default_color)
        tag = AYTag(item.key, color, label=item.label)
        tag.tag_removed.connect(self._on_tag_removed)
        tag.tag_expanded.connect(self._on_tag_expanded)

        self._tags[item.key] = tag
        self._tags_container.add_widget(tag)

    def _remove_tag(self, key: str) -> None:
        """Remove a tag widget.

        Args:
            key: Key of the tag to remove.
        """
        if key not in self._tags:
            return

        tag = self._tags.pop(key)
        tag.setParent(None)
        tag.deleteLater()

    def _emit_filter_changed(self) -> None:
        """Emit filter_changed signal with current selection."""
        self.filter_changed.emit(self.get_selected_keys())

    # --- Event Handlers ---

    def _on_toggle_dropdown(self) -> None:
        """Handle toggle button click."""
        if self._dropdown_popup is None:
            return

        if self._dropdown_visible:
            self._dropdown_popup.close()
        else:
            self._dropdown_visible = True
            self._toggle_btn.set_icon("keyboard_arrow_up")
            self._dropdown_popup.show_below(self._top_bar)

    def _on_popup_closed(self) -> None:
        """Handle popup close event."""
        self._dropdown_visible = False
        self._toggle_btn.set_icon("keyboard_arrow_down")

    def _on_tag_removed(self, key: str) -> None:
        """Handle tag X button click.

        Args:
            key: Key of the removed tag.
        """
        self._handle_tag_removed(key)

    def _on_tag_expanded(self, key: str) -> None:
        """Handle tag expand button click - toggle dropdown.

        Args:
            key: Key of the expanded tag.
        """
        self._on_toggle_dropdown()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle_dropdown()
            return
        return super().mousePressEvent(event)


class AYFilterByCategory(AYFilter):
    """Category-based filter using FilterItem list and checkbox dropdown.

    Manages a list of ``FilterItem`` objects and populates a
    ``FilterDropdownPopup`` for the user to select/deselect items.

    Signals:
        filter_changed: Inherited. Emitted with list of selected keys.
        filter_added: Inherited. Emitted when a filter is selected.
        filter_removed: Inherited. Emitted when a filter is deselected.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        label: str = "Sort by",
        items: List[FilterItem] | None = None,
        default_color: str = "#8fceff",
        variant: AYFilter.Variants = AYFilter.Variants.Low,
    ) -> None:
        """Initialize the category filter widget.

        Args:
            parent: Optional parent widget.
            label: Text displayed before the filter tags.
            items: Initial list of filter items.
            default_color: Default tag color when item has no color set.
            variant: Frame variant for background styling.
        """
        self._items: List[FilterItem] = list(items) if items else []
        super().__init__(
            parent,
            label=label,
            default_color=default_color,
            variant=variant,
        )
        self._connect_category_signals()
        self._sync_tags_from_items(self._items)

    # --- Hooks ---

    def _create_dropdown_popup(self) -> FilterDropdownPopup:
        """Create and populate the category checkbox popup.

        Returns:
            A populated ``FilterDropdownPopup`` instance.
        """
        popup = FilterDropdownPopup()
        popup.populate(self._items)
        return popup

    def _handle_tag_removed(self, key: str) -> None:
        """Deselect the filter item when its tag is dismissed.

        Args:
            key: Key of the dismissed tag.
        """
        self.set_filter_selected(key, False)

    # --- Additional signal wiring ---

    def _connect_category_signals(self) -> None:
        """Connect category-specific signals after popup is created."""
        popup = self._dropdown_popup
        if isinstance(popup, FilterDropdownPopup):
            popup.item_toggled.connect(self._on_popup_item_toggled)

    # --- Public API ---

    def add_filter(self, item: FilterItem) -> None:
        """Add a new filter option.

        Args:
            item: The FilterItem to add.
        """
        if item not in self._items:
            self._items.append(item)
            self._repopulate_popup()
            if item.selected:
                self._add_tag(item)

    def remove_filter(self, key: str) -> None:
        """Remove a filter option by key.

        Args:
            key: Unique identifier of the filter to remove.
        """
        for i, item in enumerate(self._items):
            if item.key == key:
                self._items.pop(i)
                self._remove_tag(key)
                self._repopulate_popup()
                break

    def set_filter_selected(self, key: str, selected: bool) -> None:
        """Set selection state of a filter.

        Args:
            key: Unique identifier of the filter.
            selected: New selection state.
        """
        for item in self._items:
            if item.key == key:
                if item.selected != selected:
                    item.selected = selected
                    self._update_popup_item_state(key, selected)
                    if selected:
                        self._add_tag(item)
                        self.filter_added.emit(key)
                    else:
                        self._remove_tag(key)
                        self.filter_removed.emit(key)
                    self._emit_filter_changed()
                break

    def get_selected_keys(self) -> List[str]:
        """Get list of selected filter keys.

        Returns:
            List of keys for currently selected filters.
        """
        return [item.key for item in self._items if item.selected]

    def get_selected_items(self) -> List[FilterItem]:
        """Get list of selected filter items.

        Returns:
            List of FilterItem objects that are selected.
        """
        return [item for item in self._items if item.selected]

    def clear_selection(self) -> None:
        """Deselect all filters."""
        for item in self._items:
            if item.selected:
                self.set_filter_selected(item.key, False)

    def select_all(self) -> None:
        """Select all filters."""
        for item in self._items:
            if not item.selected:
                self.set_filter_selected(item.key, True)

    # --- Private Methods ---

    def _repopulate_popup(self) -> None:
        """Repopulate the popup with current filter items."""
        popup = self._dropdown_popup
        if isinstance(popup, FilterDropdownPopup):
            popup.populate(self._items)

    def _update_popup_item_state(self, key: str, selected: bool) -> None:
        """Update checkbox state of a popup item.

        Args:
            key: Key of the item to update.
            selected: New selection state.
        """
        popup = self._dropdown_popup
        if isinstance(popup, FilterDropdownPopup):
            popup.update_item_state(key, selected)

    # --- Event Handlers ---

    def _on_popup_item_toggled(self, key: str, selected: bool) -> None:
        """Handle popup item toggle.

        Args:
            key: Key of the toggled filter.
            selected: New selection state.
        """
        self.set_filter_selected(key, selected)


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def _build() -> QtWidgets.QWidget:
        """Build test widget."""
        w = AYContainer(variant=AYContainer.Variants.High, layout_margin=10)
        w.add_widget(
            AYFilterByCategory(
                label="Sort by",
                items=[
                    FilterItem("task", "Task"),
                    FilterItem("folder", "Folder", selected=True),
                    FilterItem("status", "Status", selected=True),
                    FilterItem("priority", "Priority"),
                    FilterItem("due_date", "Due Date"),
                ],
            )
        )
        w.addStretch(10)
        return w

    test(_build, style=Style.AYONStyleOverCSS)
