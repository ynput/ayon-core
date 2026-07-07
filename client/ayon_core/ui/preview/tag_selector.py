from __future__ import annotations

import logging

from qtpy.QtWidgets import QWidget

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.tag_selector import AYTagSelector, TagData
from ayon_core.ui.preview.utils import Style, preview_widget

logger = logging.getLogger(__name__)


def build_tag_selector_preview_widget() -> QWidget:
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


if __name__ == "__main__":
    preview_widget(
        build_tag_selector_preview_widget,
        style=Style.AYONStyleOverCSS
    )
