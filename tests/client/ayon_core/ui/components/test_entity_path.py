"""Visual regression tests for AYEntityPath."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.entity_path import AYEntityPath
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


class EntityPathTest(WidgetTest):
    """Tests AYEntityPath with short and long paths."""

    size = (600, 160)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        root.add_widget(AYLabel("Short path:"))
        self._short = AYEntityPath()
        self._short.entity_path = "project/assets"
        root.add_widget(self._short)

        root.add_widget(AYLabel("Deep path:"))
        self._deep = AYEntityPath()
        self._deep.entity_path = "my_project/assets/characters/hero/modeling"
        root.add_widget(self._deep)

        root.add_widget(AYLabel("Root only:"))
        self._root = AYEntityPath()
        self._root.entity_path = "project"
        root.add_widget(self._root)

        return root

    def change_path(self) -> None:
        self._short.entity_path = "new_project/shots/sq010/sh020"

    def steps(self):
        return [self.change_path]
