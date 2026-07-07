"""Visual regression tests for AYSlicer."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.slicer import AYSlicer
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.preview.constants import EXAMPLE_STATUSES


_CATEGORIES = [
    {"text": s["text"], "icon": s["icon"], "color": s["color"]}
    for s in EXAMPLE_STATUSES
]


class SlicerTest(WidgetTest):
    """Tests AYSlicer: combo-visible state and search-field-visible state."""

    size = (500, 80)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=0,
        )
        self._slicer = AYSlicer(item_list=_CATEGORIES)
        root.add_widget(self._slicer)
        return root

    def open_search(self) -> None:
        """Toggle to search mode (hide combo, show field)."""
        self._slicer._button.setChecked(True)

    def close_search(self) -> None:
        """Toggle back to combo mode."""
        self._slicer._button.setChecked(False)

    def steps(self):
        return [self.open_search, self.close_search]
