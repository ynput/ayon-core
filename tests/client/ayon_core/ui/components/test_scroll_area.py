"""Visual regression tests for AYScrollArea and AYScrollBar."""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.scroll_area import AYScrollArea, AYScrollBar
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.frame import AYFrame


class ScrollAreaTest(WidgetTest):
    """Tests AYScrollArea with scrollable content and AYScrollBar."""

    size = (400, 300)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=10,
            layout_spacing=10,
        )

        root.add_widget(AYLabel("Scroll area with many items:"))

        self._scroll = AYScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(200)

        content = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=10,
            layout_spacing=8,
        )

        # Add enough items to require scrolling
        for i in range(20):
            frame = AYFrame(variant=AYFrame.Variants.Low)
            frame.setFixedHeight(32)
            lbl = AYLabel(f"Item {i + 1:02d}", parent=frame)
            lbl.setContentsMargins(8, 0, 0, 0)
            from ayon_core.ui.components.layouts import AYHBoxLayout

            lyt = AYHBoxLayout(frame, margin=4)
            lyt.addWidget(lbl)
            content.add_widget(frame)

        self._scroll.setWidget(content)
        root.add_widget(self._scroll, stretch=1)

        # Standalone scroll bars
        row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=10,
        )
        row.add_widget(AYLabel("Vertical scrollbar:"))
        self._vbar = AYScrollBar()
        self._vbar.setFixedHeight(32)
        self._vbar.setRange(0, 100)
        self._vbar.setValue(40)
        row.add_widget(self._vbar)

        row.add_widget(AYLabel("Horizontal scrollbar:"))
        self._hbar = AYScrollBar()
        self._hbar.setFixedWidth(200)
        self._hbar.setOrientation(Qt.Orientation.Horizontal)
        self._hbar.setRange(0, 100)
        self._hbar.setValue(60)
        row.add_widget(self._hbar)
        row.addStretch(1)
        root.add_widget(row)

        return root

    def scroll_down(self) -> None:
        """Scroll to near the bottom."""
        self._scroll.verticalScrollBar().setValue(300)

    def scroll_bars_edges(self) -> None:
        """Move scroll bars to extremes."""
        self._scroll.verticalScrollBar().setValue(0)
        self._vbar.setValue(0)
        self._hbar.setValue(100)

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.scroll_down, self.scroll_bars_edges]
