from __future__ import annotations

from enum import Enum

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QLayout, QLayoutItem, QWidget

from ..variants import QFrameVariants
from .frame import AYFrame
from .layouts import (
    AYFlowLayout,
    AYGridLayout,
    AYHBoxLayout,
    AYVBoxLayout,
    AYFormLayout,
)


class AYContainer(AYFrame):
    class Layout(Enum):
        HBox = 0
        VBox = 1
        Grid = 2
        Flow = 3
        Form = 4

    Variants = QFrameVariants

    def __init__(
        self,
        *args,
        layout: Layout = Layout.HBox,
        variant: Variants = Variants.Default,
        margin: int = 0,
        layout_spacing: int | tuple[int, int] = 0,
        layout_margin: int = 0,
        bg_tint: str = "",
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
            variant=variant,
            margin=margin,
            bg_tint=bg_tint,
        )
        self._variant_str: str = variant.value
        if layout == AYContainer.Layout.HBox:
            assert isinstance(layout_spacing, int)
            self._layout = AYHBoxLayout(
                self, spacing=layout_spacing, margin=layout_margin
            )
        elif layout == AYContainer.Layout.VBox:
            assert isinstance(layout_spacing, int)
            self._layout = AYVBoxLayout(
                self, spacing=layout_spacing, margin=layout_margin
            )
        elif layout == AYContainer.Layout.Grid:
            assert isinstance(layout_spacing, int)
            self._layout = AYGridLayout(
                self, spacing=layout_spacing, margin=layout_margin
            )
        elif layout == AYContainer.Layout.Flow:
            assert isinstance(layout_spacing, int)
            self._layout = AYFlowLayout(
                self, spacing=layout_spacing, margin=layout_margin
            )
        elif layout == AYContainer.Layout.Form:
            assert (
                isinstance(layout_spacing, tuple) and len(layout_spacing) == 2
            )
            self._layout = AYFormLayout(
                self, spacing=layout_spacing, margin=layout_margin
            )
        else:
            raise ValueError(f"Unknown Layout type : {layout}")

    def add_widget(
        self,
        w: QWidget,
        stretch: int = 0,
        row: int = 0,
        column: int = 0,
        alignment: Qt.AlignmentFlag = 0,  # type: ignore
    ):
        if isinstance(self._layout, (AYHBoxLayout, AYVBoxLayout)):
            self._layout.addWidget(w, stretch=stretch)
        elif isinstance(self._layout, AYGridLayout):
            self._layout.addWidget(w, row, column, alignment)
        elif isinstance(self._layout, AYFlowLayout):
            self._layout.addWidget(w)
        else:
            raise ValueError(f"Unknown Layout type : {self._layout}")

    def add_layout(
        self,
        lyt: QLayout,
        stretch: int = 0,
        row: int = 0,
        column: int = 0,
        alignment: Qt.AlignmentFlag = 0,  # type: ignore
    ):
        if isinstance(self._layout, (AYHBoxLayout, AYVBoxLayout)):
            self._layout.addLayout(lyt, stretch=stretch)
        elif isinstance(self._layout, AYGridLayout):
            self._layout.addLayout(lyt, row, column, alignment)
        elif isinstance(self._layout, AYFlowLayout):
            self._layout.addLayout(lyt)
        else:
            raise ValueError(f"Unknown Layout type : {self._layout}")

    def insert_widget(self, index: int, w: QWidget, stretch: int = 0):
        if isinstance(self._layout, (AYHBoxLayout, AYVBoxLayout)):
            if isinstance(w, QWidget):
                self._layout.insertWidget(index, w, stretch=stretch)
        elif isinstance(self._layout, (AYGridLayout, AYFlowLayout)):
            raise ValueError(f"Not supported by this layout : {self._layout}")

    def add_row(self, *args, **kwargs):
        if isinstance(self._layout, AYFormLayout):
            self._layout.addRow(*args, **kwargs)
        else:
            raise ValueError(f"Not supported by this layout : {self._layout}")

    def insert_row(self, index: int, *args, **kwargs):
        if isinstance(self._layout, AYFormLayout):
            self._layout.insertRow(index, *args, **kwargs)
        else:
            raise ValueError(f"Not supported by this layout : {self._layout}")

    def set_label_alignment(self, alignment: Qt.AlignmentFlag):
        if isinstance(self._layout, AYFormLayout):
            self._layout.setLabelAlignment(alignment)
        else:
            raise ValueError(f"Not supported by this layout : {self._layout}")

    def count(self) -> int:
        return self._layout.count()

    def addStretch(self, stretch: int = 0) -> None:
        if isinstance(self._layout, (AYGridLayout, AYFlowLayout)):
            return
        self._layout.addStretch(stretch=stretch)

    def takeAt(self, index: int) -> QLayoutItem:
        return self._layout.takeAt(index)  # type: ignore

    def itemAt(self, index: int) -> QLayoutItem:
        if isinstance(self._layout, AYGridLayout):
            raise NotImplementedError
        return self._layout.itemAt(index)  # type: ignore

    def clear(self):
        self._layout.clear()


if __name__ == "__main__":
    from ayon_core.ui.tester import Style, test
    from ayon_core.ui.components.label import AYLabel

    def build():
        w = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=10,
            layout_margin=10,
        )
        w.add_widget(
            AYContainer(
                layout=AYContainer.Layout.VBox,
                variant=AYContainer.Variants.High,
                layout_margin=10,
            )
        )
        w.add_widget(
            AYContainer(
                layout=AYContainer.Layout.VBox,
                variant=AYContainer.Variants.High,
                layout_margin=10,
            )
        )
        w.add_widget(
            AYContainer(
                layout=AYContainer.Layout.Form,
                variant=AYContainer.Variants.High,
                layout_margin=10,
                layout_spacing=(32, 10),
            )
        )
        last_widget = w._layout.itemAt(2).widget()  # type: ignore
        assert isinstance(last_widget, AYContainer)
        last_widget.set_label_alignment(Qt.AlignRight)
        last_widget.add_row(AYLabel("Label:", dim=True), AYLabel("Value"))
        last_widget.add_row(
            AYLabel("Another Label:", dim=True), AYLabel("Another Value")
        )
        w.setMinimumWidth(200)
        w.setMinimumHeight(400)
        return w

    test(build, style=Style.AyonStyleOverCSS)
