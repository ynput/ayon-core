"""Visual regression tests for AYFrame."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.frame import AYFrame
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


class FrameTest(WidgetTest):
    """Tests AYFrame across all non-debug variants."""

    size = (500, 500)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=8,
        )

        for variant in AYFrame.Variants:
            # Skip debug variants — they exist for development tooling only
            if variant.value.startswith("debug"):
                continue
            frame = AYFrame(variant=variant)
            frame.setFixedHeight(36)

            lbl = AYLabel(variant.value, parent=frame)
            lbl.setContentsMargins(8, 0, 0, 0)
            from ayon_core.ui.components.layouts import AYHBoxLayout

            lyt = AYHBoxLayout(frame, margin=4)
            lyt.addWidget(lbl)

            root.add_widget(frame)

        return root

    def steps(self):
        return []
