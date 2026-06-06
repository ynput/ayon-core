"""Tag selector component for displaying and managing tags.

This module provides an AYTagSelector widget that displays a button with
selected tags as badges, and opens a floating dropdown for tag selection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtGui import QColor, QFocusEvent, QShowEvent
from qtpy.QtWidgets import (
    QApplication,
    QSizePolicy,
    QWidget,
)

from ..style import get_ayon_style
from .buttons import AYButton
from .container import AYContainer
from .dropdown import AYDropdownPopup
from .filterable_list import FilterableList
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYHBoxLayout, AYVBoxLayout
from .style_mixin import StyleMixin

logger = logging.getLogger(__name__)


@dataclass
class TagData:
    """Data class representing a tag with name and color.

    Attributes:
        name: The display name of the tag.
        color: The hex color string for the tag (e.g., "#4ECDC4").
    """

    name: str
    color: str = "#8b9198"


class TagItemWidget(AYButton):
    """A clickable tag item widget used in the dropdown list.

    Displays a tag with its color and handles selection state.
    Inherits from AYButton to leverage built-in click handling,
    hover states, and checkable functionality.

    Attributes:
        tag_clicked: Signal emitted when the tag item is clicked (tag name).
    """

    tag_clicked = Signal(str)

    def __init__(
        self,
        tag: TagData,
        selected: bool = False,
        parent: QWidget | None = None,
    ):
        """Initialize the tag item widget.

        Args:
            tag: The TagData object with name and color.
            selected: Whether the tag is currently selected.
            parent: Optional parent widget.
        """
        self._tag = tag
        super().__init__(
            tag.name,
            variant=AYButton.Variants.Tag_Menu,
            fixed_width=False,
            icon_color=tag.color,
            checkable=True,
            parent=parent,
        )

        self.setChecked(selected)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        # Connect the built-in clicked signal to emit tag name
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        """Handle button click to emit tag_clicked signal with tag name."""
        self.tag_clicked.emit(self._tag.name)

    @property
    def tag(self) -> TagData:
        """Return the tag data."""
        return self._tag

    @property
    def selected(self) -> bool:
        """Return the selection state."""
        return self.isChecked()

    @selected.setter
    def selected(self, value: bool) -> None:
        """Set the selection state."""
        self.setChecked(value)

    @property
    def tag_color(self) -> str:
        """Return the tag color."""
        return self._tag.color


class TagDropdown(AYDropdownPopup):
    """A floating dropdown window for tag selection.

    Features a search field and a scrollable list of tags. New tags can be
    created by typing a non-existing tag name and pressing Enter.

    Attributes:
        tag_toggled: Signal emitted when a tag is toggled (name, selected).
        add_new_tag: Signal emitted when user wants to add a new tag (name).
        closed: Signal emitted when the dropdown is closed.
    """

    tag_toggled = Signal(str, bool)
    add_new_tag = Signal(str)
    closed = Signal()

    def __init__(
        self,
        tags: list[TagData],
        selected_tags: list[str],
        min_width: int = 200,
        parent: QWidget | None = None,
    ):
        """Initialize the dropdown window.

        Args:
            tags: List of all available tags.
            selected_tags: List of currently selected tag names.
            parent: Optional parent widget.
        """
        super().__init__(
            parent=parent,
            variant=AYFrame.Variants.Low_Framed,
            translucent_bg=False,
        )
        # Internal container to hold the actual widgets and layout
        self._content = AYVBoxLayout(self, margin=1)
        self._tags = tags
        self._selected_tags = set(selected_tags)
        self._tag_widgets: dict[str, TagItemWidget] = {}

        self.setMinimumWidth(min_width)
        self.setMaximumHeight(400)

        # Propagate popup closed signal to a local closed signal
        self.popup_closed.connect(self.closed.emit)

        self._build()

    def _build(self) -> None:
        """Build the dropdown UI layout."""
        self._filterable_list = FilterableList(
            placeholder="Search tags...",
            parent=self,
        )
        search = self._filterable_list.search_field()
        search.textChanged.connect(self._on_search_changed)
        search.returnPressed.connect(self._on_enter_pressed)
        self._content.addWidget(self._filterable_list)

        # Populate tags
        self._populate_tags()

    def _populate_tags(self) -> None:
        """Populate the tag list with tag item widgets."""
        if not self._tags:
            tag = TagData("No available tags", color="#ffffff")
            tag_widget = TagItemWidget(tag)
            tag_widget.setEnabled(False)
            self._tag_widgets[tag.name] = tag_widget
            self._filterable_list.add_item(tag_widget)
            return

        for tag in self._tags:
            selected = tag.name in self._selected_tags
            tag_widget = TagItemWidget(tag, selected=selected)
            tag_widget.tag_clicked.connect(self._on_tag_clicked)
            self._tag_widgets[tag.name] = tag_widget
            tag_name = tag.name
            self._filterable_list.add_item(
                tag_widget,
                match_fn=lambda text, n=tag_name: (
                    not text.lower().strip()
                    or text.lower().strip() in n.lower()
                ),
            )

        self._filterable_list.add_stretch()

    def _on_search_changed(self, text: str) -> None:
        """Filter tags based on search input.

        Args:
            text: The current search text.
        """
        self._adjust_height()

    def _on_enter_pressed(self) -> None:
        """Handle Enter key press to create new tag if it doesn't exist."""
        text = self._filterable_list.search_field().text().strip()
        if not text:
            return

        # Check if the tag already exists (case-insensitive)
        existing_tag = None
        for tag in self._tags:
            if tag.name.lower() == text.lower():
                existing_tag = tag
                break

        if existing_tag:
            # Toggle the existing tag
            widget = self._tag_widgets.get(existing_tag.name)
            if widget:
                new_state = not widget.isChecked()
                widget.setChecked(new_state)
                if new_state:
                    self._selected_tags.add(existing_tag.name)
                else:
                    self._selected_tags.discard(existing_tag.name)
                self.tag_toggled.emit(existing_tag.name, new_state)
        else:
            # Create new tag
            self.add_new_tag.emit(text)

        self._filterable_list.search_field().clear()

    def _on_tag_clicked(self, tag_name: str) -> None:
        """Handle tag item click to toggle selection.

        Args:
            tag_name: The name of the clicked tag.
        """
        widget = self._tag_widgets.get(tag_name)
        if widget:
            new_state = widget.isChecked()
            if new_state:
                self._selected_tags.add(tag_name)
            else:
                self._selected_tags.discard(tag_name)
            self.tag_toggled.emit(tag_name, new_state)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Handle focus out to close dropdown."""
        # Check if focus is going to a child widget
        focus_widget = QApplication.focusWidget()
        if focus_widget and self.isAncestorOf(focus_widget):
            return
        self.close()
        self.closed.emit()
        super().focusOutEvent(event)

    def get_selected_tags(self) -> list[str]:
        """Return the list of currently selected tag names.

        Returns:
            List of selected tag names.
        """
        return list(self._selected_tags)

    def _calculate_content_height(self) -> int:
        """Calculate the ideal height based on visible content."""
        search_height = 40  # search field + margins

        tags_height = sum(
            w.sizeHint().height()
            for w in self._filterable_list.visible_items()
        )

        margin = 2  # layout_margin from __init__
        return search_height + tags_height + (margin * 2)

    def _adjust_height(self) -> None:
        """Adjust dropdown height to fit content up to max height."""
        max_height = 400
        content_height = self._calculate_content_height()
        self.setFixedHeight(min(content_height, max_height))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._filterable_list.search_field().setFocus()
        self._adjust_height()


class AYTagSelector(StyleMixin, QWidget):
    """A tag selector widget with button and floating dropdown.

    Displays a button with a tag icon. When tags are selected, they appear
    as badges next to the button. Clicking the button opens a floating
    dropdown for tag selection.

    Attributes:
        tags_changed: Signal emitted when selected tags change.
    """

    tags_changed = Signal(list)

    def __init__(
        self,
        available_tags: list[TagData] | list[dict] | list[str] | None = None,
        selected_tags: list[str] | None = None,
        max_visible_tags: int = 4,
        min_width: int = 200,
        parent: QWidget | None = None,
    ):
        """Initialize the tag selector.

        Args:
            available_tags: List of available tags. Can be TagData objects,
                dicts with 'name' and 'color' keys, or simple strings.
            selected_tags: List of initially selected tag names.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setStyle(get_ayon_style())

        self._available_tags = self._normalize_tags(available_tags or [])
        self._selected_tags: list[str] = list(selected_tags or [])
        self._dropdown: TagDropdown | None = None
        self._max_visible_tags = max_visible_tags
        self._min_width = min_width

        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )

        self._build()
        self._update_badges()

    @staticmethod
    def _normalize_tags(
        tags: list[TagData] | list[dict] | list[str],
    ) -> list[TagData]:
        """Normalize various tag input formats to TagData objects.

        Args:
            tags: List of tags in any supported format.

        Returns:
            List of TagData objects.
        """
        normalized: list[TagData] = []
        for tag in tags:
            if isinstance(tag, TagData):
                normalized.append(tag)
            elif isinstance(tag, dict):
                name = tag.get("name") or tag.get("text") or str(tag)
                color = tag.get("color", "#8b9198")
                normalized.append(TagData(name=name, color=color))
            else:
                normalized.append(TagData(name=str(tag)))
        return sorted(normalized, key=lambda t: t.name.lower())

    def _build(self) -> None:
        """Build the main widget UI layout."""
        self._main_layout = AYHBoxLayout(margin=0, spacing=4)
        self.setLayout(self._main_layout)

        # Main button with tag icon
        self._button = AYButton(
            icon="sell",
            variant=AYButton.Variants.Nav,
            tooltip="Select tags",
        )
        self._button.clicked.connect(self._show_dropdown)
        self._main_layout.addWidget(self._button)

        # Container for selected tag badges
        self._badges_container = AYFrame(variant=AYFrame.Variants.Low)
        self._badges_layout = AYHBoxLayout(margin=0, spacing=4)
        self._badges_container.setLayout(self._badges_layout)
        self._main_layout.addWidget(self._badges_container)

        self._main_layout.addStretch()

    def _update_badges(self) -> None:
        """Update the display of selected tag badges."""
        # Clear existing badges
        while self._badges_layout.count() > 0:
            item = self._badges_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Create badges for selected tags
        tag_color_map = {tag.name: tag.color for tag in self._available_tags}
        for i, tag_name in enumerate(self._selected_tags):
            if i >= self._max_visible_tags:
                remaining_tags = (
                    len(self._selected_tags) - self._max_visible_tags
                )
                badge = AYLabel(
                    f"+{remaining_tags}",
                    variant=AYLabel.Variants.Default,
                    rel_text_size=-2,
                )
                self._badges_layout.addWidget(badge)
                break
            color = tag_color_map.get(tag_name, "#8b9198")
            badge = AYLabel(
                tag_name,
                icon_color=color,
                variant=AYLabel.Variants.Badge,
                rel_text_size=-2,
                contrast_color=QColor(color),
            )
            self._badges_layout.addWidget(badge)

    def _show_dropdown(self) -> None:
        """Show the floating dropdown for tag selection."""
        if self._dropdown is not None:
            self._dropdown.close()
            self._dropdown = None
            return

        self._dropdown = TagDropdown(
            tags=self._available_tags,
            selected_tags=self._selected_tags,
            min_width=self._min_width,
            parent=None,
        )
        self._dropdown.tag_toggled.connect(self._on_tag_toggled)
        self._dropdown.add_new_tag.connect(self._on_add_new_tag)
        self._dropdown.closed.connect(self._on_dropdown_closed)

        # Position dropdown below the button using helper from AYDropdownPopup
        self._dropdown.show_below(self._button)

    def _on_tag_toggled(self, tag_name: str, selected: bool) -> None:
        """Handle tag toggle from dropdown.

        Args:
            tag_name: The name of the toggled tag.
            selected: Whether the tag is now selected.
        """
        if selected:
            if tag_name not in self._selected_tags:
                self._selected_tags.append(tag_name)
        else:
            if tag_name in self._selected_tags:
                self._selected_tags.remove(tag_name)

        self._update_badges()
        self.tags_changed.emit(self._selected_tags.copy())

    def _on_add_new_tag(self, tag_name: str) -> None:
        """Handle adding a new tag.

        Args:
            tag_name: The name of the new tag to add.
        """
        # Check if tag already exists
        existing_names = {tag.name.lower() for tag in self._available_tags}
        if tag_name.lower() in existing_names:
            logger.warning("Tag '%s' already exists", tag_name)
            return

        # Add new tag with default color
        new_tag = TagData(name=tag_name, color="#8b9198")
        self._available_tags.append(new_tag)
        self._available_tags.sort(key=lambda t: t.name.lower())

        # Select the new tag
        if tag_name not in self._selected_tags:
            self._selected_tags.append(tag_name)

        self._update_badges()
        self.tags_changed.emit(self._selected_tags.copy())

        # Refresh dropdown if open
        if self._dropdown:
            self._dropdown.close()
            self._show_dropdown()

    def _on_dropdown_closed(self) -> None:
        """Handle dropdown close event."""
        self._dropdown = None

    def get_selected_tags(self) -> list[str]:
        """Get the list of selected tag names.

        Returns:
            List of selected tag names.
        """
        return self._selected_tags.copy()

    def set_selected_tags(self, tags: list[str]) -> None:
        """Set the selected tags.

        Args:
            tags: List of tag names to select.
        """
        self._selected_tags = list(tags)
        self._update_badges()
        self.tags_changed.emit(self._selected_tags.copy())

    def set_available_tags(
        self,
        tags: list[TagData] | list[dict] | list[str],
    ) -> None:
        """Set the available tags.

        Args:
            tags: List of tags in any supported format.
        """
        self._available_tags = self._normalize_tags(tags)
        # Remove selected tags that no longer exist
        available_names = {tag.name for tag in self._available_tags}
        self._selected_tags = [
            t for t in self._selected_tags if t in available_names
        ]
        self._update_badges()


# TEST ========================================================================


if __name__ == "__main__":
    from ..tester import Style, test

    def _build() -> QWidget:
        """Build the test widget."""
        # Sample tags with different colors matching the UX design
        sample_tags = [
            TagData(name="birds", color="#4ECDC4"),  # Cyan
            TagData(name="animals", color="#F4D03F"),  # Yellow/gold
            TagData(name="humans", color="#E67E22"),  # Orange/coral
            TagData(name="robots", color="#95A5A6"),  # Gray
            TagData(name="sets", color="#27AE60"),  # Green
            TagData(name="street", color="#7F8C8D"),  # Gray
            TagData(name="house", color="#8E9A6D"),  # Olive/green
            TagData(name="vegetation", color="#2ECC71"),  # Green
            TagData(name="vehicles", color="#3498DB"),  # Blue
            TagData(name="water", color="#1ABC9C"),  # Teal
        ]

        # Create main container
        container = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=16,
            layout_spacing=16,
        )

        # Add a label
        title_label = AYLabel(
            "Tag Selector Demo",
            bold=True,
            rel_text_size=4,
        )
        container.add_widget(title_label)

        # Create tag selector with some pre-selected tags
        tag_selector = AYTagSelector(
            available_tags=sample_tags,
            selected_tags=["birds", "animals"],
        )

        # Connect signal to log changes
        tag_selector.tags_changed.connect(
            lambda tags: logger.info("Selected tags: %s", tags)
        )

        container.add_widget(tag_selector)

        # Add another tag selector without pre-selected tags
        container.add_widget(AYLabel("Another Empty Tag Selector:", dim=True))
        tag_selector_empty = AYTagSelector(available_tags=sample_tags)
        container.add_widget(tag_selector_empty)

        # Add another tag selector without any defined tags
        container.add_widget(
            AYLabel("Tag Selector with an empty tag list:", dim=True)
        )
        tag_selector_empty = AYTagSelector(available_tags=[])
        container.add_widget(tag_selector_empty)

        container.addStretch()
        container.setMinimumWidth(400)
        container.setMinimumHeight(300)

        return container

    # Configure logging for the test
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    test(_build, style=Style.AyonStyleOverCSS)
