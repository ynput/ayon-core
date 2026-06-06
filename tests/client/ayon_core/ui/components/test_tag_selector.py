"""Visual regression tests for AYTagSelector."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.tag_selector import AYTagSelector, TagData
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


_AVAILABLE_TAGS = [
    TagData(name="feature",   color="#3498db"),
    TagData(name="bug",       color="#cb1a1a"),
    TagData(name="approved",  color="#00f0b4"),
    TagData(name="on-hold",   color="#fa6e46"),
    TagData(name="wip",       color="#bababa"),
    TagData(name="omitted",   color="#434a56"),
]


class TagSelectorTest(WidgetTest):
    """Tests AYTagSelector: empty, with pre-selected tags, and badge overflow."""

    size = (700, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        root.add_widget(AYLabel("No selection:"))
        self._empty = AYTagSelector(available_tags=_AVAILABLE_TAGS)
        root.add_widget(self._empty)

        root.add_widget(AYLabel("Two tags selected:"))
        self._two_selected = AYTagSelector(
            available_tags=_AVAILABLE_TAGS,
            selected_tags=["feature", "bug"],
        )
        root.add_widget(self._two_selected)

        root.add_widget(AYLabel("Many tags selected (badge overflow):"))
        self._many_selected = AYTagSelector(
            available_tags=_AVAILABLE_TAGS,
            selected_tags=["feature", "bug", "approved", "on-hold", "wip", "omitted"],
            max_visible_tags=3,
        )
        root.add_widget(self._many_selected)

        return root

    def add_tag(self) -> None:
        self._empty._available_tags = _AVAILABLE_TAGS
        self._empty._selected_tags = ["approved"]
        self._empty._update_badges()

    def steps(self):
        return [self.add_tag]
