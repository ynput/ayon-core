"""A widget with a search field and a scrollable, filterable list."""

from __future__ import annotations

from typing import Callable

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QFrame, QWidget

from .container import AYContainer
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYVBoxLayout
from .line_edit import AYLineEdit
from .scroll_area import AYScrollArea
from .style_mixin import StyleMixin


class FilterableList(StyleMixin, QWidget):
    """A widget with a search field and a scrollable, filterable list.

    Items are added as QWidget instances. Each item is matched against the
    search text using a caller-supplied key function.

    Attributes:
        search_placeholder: Placeholder text shown in the search field.
    """

    def __init__(
        self,
        placeholder: str = "Search...",
        parent: QWidget | None = None,
    ):
        """Initialize the filterable list.

        Args:
            placeholder: Placeholder text for the search input.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._items: list[tuple[QWidget, Callable[[str], bool]]] = []
        self._placeholder = placeholder
        self._build()

    def _build(self) -> None:
        """Build the internal UI layout."""
        layout = AYVBoxLayout(self, margin=0, spacing=0)

        search_container = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYFrame.Variants.Low_Square,
            layout_margin=6,
            layout_spacing=6,
        )
        self.search_icon = AYLabel(
            icon="search",
            icon_size=18,
            icon_color="#ffffff",
            variant=AYLabel.Variants.Default,
        )
        search_container.add_widget(self.search_icon)

        self._search_field = AYLineEdit()
        self._search_field.setPlaceholderText(self._placeholder)
        self._search_field.textChanged.connect(self._on_search_changed)
        search_container.add_widget(self._search_field)
        layout.addWidget(search_container)

        scroll_area = AYScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self._items_container = AYFrame(variant=AYFrame.Variants.Low)
        self._items_layout = AYVBoxLayout(margin=0, spacing=0)
        self._items_layout.setAlignment(Qt.AlignTop)
        self._items_container.setLayout(self._items_layout)
        scroll_area.setWidget(self._items_container)
        layout.addWidget(scroll_area)

    def add_item(
        self,
        widget: QWidget,
        match_fn: Callable[[str], bool] | None = None,
    ) -> None:
        """Add a widget to the filterable list.

        Args:
            widget: The widget to add.
            match_fn: A callable that receives the current search text and
                returns True if the widget should be visible. When omitted
                the item is always visible.
        """
        if match_fn is None:
            match_fn = lambda _: True  # noqa: E731
        self._items.append((widget, match_fn))
        self._items_layout.addWidget(widget)

    def add_stretch(self) -> None:
        """Add a stretch spacer at the end of the list."""
        self._items_layout.addStretch()

    def clear_items(self) -> None:
        """Remove all items from the list."""
        self._items.clear()
        self._items_layout.clear()

    def search_field(self) -> AYLineEdit:
        """Return the search field widget.

        Returns:
            The internal AYLineEdit used for filtering.
        """
        return self._search_field

    def visible_items(self) -> list[QWidget]:
        """Return currently visible item widgets.

        Returns:
            List of visible QWidget instances.
        """
        return [w for w, _ in self._items if w.isVisible()]

    def _on_search_changed(self, text: str) -> None:
        """Filter items based on search text.

        Args:
            text: Current search text.
        """
        for widget, match_fn in self._items:
            widget.setVisible(match_fn(text))
