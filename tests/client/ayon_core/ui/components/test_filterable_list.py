"""Visual regression tests for FilterableList."""

from __future__ import annotations

from qtpy.QtGui import QColor
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.filterable_list import FilterableList
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.tag import AYTag


class FilterableListTest(WidgetTest):
    """Tests FilterableList: empty, with items, and filtered state."""

    size = (400, 300)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=10,
            layout_spacing=10,
        )

        root.add_widget(AYLabel("Filterable list with tags:"))
        self._list = FilterableList(placeholder="Search tags...")

        # Add some tag items
        tag_configs = [
            ("feature", QColor("#3498db")),
            ("bug", QColor("#cb1a1a")),
            ("approved", QColor("#00f0b4")),
            ("on-hold", QColor("#fa6e46")),
            ("wip", QColor("#bababa")),
            ("omitted", QColor("#434a56")),
        ]
        for name, color in tag_configs:
            tag = AYTag(name=name, color=color)
            self._list.add_item(
                tag,
                match_fn=lambda text, n=name: n.lower().startswith(
                    text.lower()
                ),
            )

        self._list.add_stretch()
        root.add_widget(self._list, stretch=1)

        return root

    def filter_items(self) -> None:
        """Type in search to filter items down."""
        self._list.search_field().setText("ap")

    def clear_filter(self) -> None:
        """Clear the search field."""
        self._list.search_field().clear()

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.filter_items, self.clear_filter]
