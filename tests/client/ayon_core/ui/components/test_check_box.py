"""Visual regression tests for AYCheckBox."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import AYContainer


class CheckBoxTest(WidgetTest):
    """Tests all AYCheckBox variants across checked/unchecked states."""

    size = (400, 300)
    tolerance = 0.0

    def build(self) -> QWidget:
        container = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )
        self._checkboxes: list[AYCheckBox] = []
        for variant in AYCheckBox.Variants:
            cb = AYCheckBox(f"{variant.name} Checkbox", variant=variant)
            container.add_widget(cb)
            self._checkboxes.append(cb)
        return container

    def check_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(True)

    def uncheck_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(False)

    def steps(self):
        return [self.check_all, self.uncheck_all]
