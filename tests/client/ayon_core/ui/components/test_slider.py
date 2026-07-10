"""Visual regression tests for AYSlider."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.slider import AYSlider
from ayon_core.ui.components.container import AYContainer


class SliderTest(WidgetTest):
    """Tests AYSlider with default, disabled, and stepped variants."""

    size = (420, 260)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=10,
        )

        # Default slider matching the mockup.
        self._grid_size = AYSlider(
            label="Grid size",
            value=220,
            minimum=0,
            maximum=500,
            step=1,
        )
        root.add_widget(self._grid_size)

        # Disabled state.
        self._disabled = AYSlider(
            label="Opacity (disabled)",
            value=50,
            minimum=0,
            maximum=100,
        )
        self._disabled.setEnabled(False)
        root.add_widget(self._disabled)

        # Stepped slider.
        self._stepped = AYSlider(
            label="Step 10",
            value=30,
            minimum=0,
            maximum=100,
            step=10,
        )
        root.add_widget(self._stepped)

        # min position.
        self._min_pos = AYSlider(
            label="Min position",
            value=0,
            minimum=0,
            maximum=100,
            step=10,
        )
        root.add_widget(self._min_pos)

        # max position.
        self._max_pos = AYSlider(
            label="Max position",
            value=100,
            minimum=0,
            maximum=100,
            step=10,
        )
        root.add_widget(self._max_pos)
        root.addStretch()

        return root

    def set_value_min(self) -> None:
        self._grid_size.setValue(0)

    def set_value_max(self) -> None:
        self._grid_size.setValue(500)

    def disable_stepped(self) -> None:
        self._stepped.setEnabled(False)

    def steps(self):
        return [
            self.set_value_min,
            self.set_value_max,
            self.disable_stepped,
        ]
