"""Visual regression tests for AYFilterByCategory."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.filter import AYFilterByCategory, FilterItem
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


_FILTER_ITEMS = [
    FilterItem(key="animation", label="Animation", color="#3498db"),
    FilterItem(key="modeling", label="Modeling", color="#fa6e46"),
    FilterItem(key="rigging", label="Rigging", color="#00f0b4"),
    FilterItem(key="lookdev", label="Lookdev", color="#f4c430"),
    FilterItem(key="compositing", label="Compositing", color="#cb1a1a"),
]


class FilterTest(WidgetTest):
    """Tests AYFilterByCategory with no selection and with some filters
    selected."""

    size = (600, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        root.add_widget(AYLabel("No filters active:"))
        self._filter_empty = AYFilterByCategory(
            label="Filter by",
            items=list(_FILTER_ITEMS),
        )
        root.add_widget(self._filter_empty)

        root.add_widget(AYLabel("Some filters active:"))
        active_items = [
            FilterItem(
                key=i.key,
                label=i.label,
                color=i.color,
                selected=(i.key in ("animation", "rigging")),
            )
            for i in _FILTER_ITEMS
        ]
        self._filter_active = AYFilterByCategory(
            label="Filter by",
            items=active_items,
        )
        root.add_widget(self._filter_active)

        return root

    def select_more(self) -> None:
        self._filter_empty.set_filter_selected("modeling", True)
        self._filter_empty.set_filter_selected("lookdev", True)

    def deselect_all(self) -> None:
        for item in self._filter_active._items:
            self._filter_active.set_filter_selected(item.key, False)

    def steps(self):
        return [self.select_more, self.deselect_all]
