"""Visual regression tests for AYTag."""

from __future__ import annotations

from qtpy.QtGui import QColor
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.tag import AYTag
from ayon_core.ui.components.container import AYContainer


# Representative tag configs: (name, color_hex, optional_label)
_TAG_CONFIGS = [
    ("feature", "#3498db", None),
    ("bug", "#cb1a1a", None),
    ("approved", "#00f0b4", None),
    ("on-hold", "#fa6e46", None),
    ("wip", "#bababa", "Work in progress"),
    ("omitted", "#434a56", None),
    ("light", "#f8f8f8", "Light bg"),
]


class TagTest(WidgetTest):
    """Tests AYTag with various background colours (dark/light) and labels."""

    size = (700, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.Flow,
            layout_margin=20,
            layout_spacing=8,
        )

        for name, color_hex, label in _TAG_CONFIGS:
            tag = AYTag(
                name=name,
                color=QColor(color_hex),
                label=label,
            )
            root.add_widget(tag)

        return root

    def steps(self):
        return []
