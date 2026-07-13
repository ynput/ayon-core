"""Visual regression tests for AYLineEdit."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.line_edit import AYLineEdit
from ayon_core.ui.components.container import AYContainer


class LineEditTest(WidgetTest):
    """Tests AYLineEdit across Default and Search_Field variants, plus
    disabled."""

    size = (500, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        # Default variant - empty, with placeholder, with text
        row1 = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
            layout_spacing=8,
        )
        self._empty = AYLineEdit(
            variant=AYLineEdit.Variants.Default,
            placeholder="Empty (placeholder visible)",
        )
        row1.add_widget(self._empty)

        self._with_text = AYLineEdit(variant=AYLineEdit.Variants.Default)
        self._with_text.setText("Some entered text")
        row1.add_widget(self._with_text)

        # Search-field variant
        self._search = AYLineEdit(
            variant=AYLineEdit.Variants.Search_Field,
            placeholder="Search…",
        )
        row1.add_widget(self._search)

        # Disabled state
        self._disabled = AYLineEdit(
            variant=AYLineEdit.Variants.Default,
            placeholder="Disabled input",
        )
        self._disabled.setEnabled(False)
        row1.add_widget(self._disabled)

        root.add_widget(row1)
        return root

    def set_text_in_search(self) -> None:
        self._search.setText("hello world")

    def clear_all(self) -> None:
        self._search.clear()
        self._with_text.clear()

    def steps(self):
        return [self.set_text_in_search, self.clear_all]
