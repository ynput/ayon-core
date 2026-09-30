"""Visual regression tests for AYTextEdit."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.text_edit import AYTextEdit
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel

_SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog.\n"
    "Line two with some more content here."
)


class TextEditTest(WidgetTest):
    """Tests AYTextEdit across Default, Low, and High variants."""

    size = (600, 400)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        for variant in AYTextEdit.Variants:
            # Skip debug variants — they exist for development only
            if variant.value.startswith("debug"):
                continue
            row = AYContainer(
                layout=AYContainer.Layout.VBox,
                layout_margin=0,
                layout_spacing=4,
            )
            row.add_widget(AYLabel(f"Variant: {variant.name}"))
            edit = AYTextEdit(variant=variant)
            edit.setFixedHeight(80)
            edit.setPlainText(_SAMPLE_TEXT)
            row.add_widget(edit)
            root.add_widget(row)

        return root

    def steps(self):
        return []
