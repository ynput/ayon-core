"""ButtonDrawer: custom painting for QPushButton."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtGui import QPainter
from qtpy.QtWidgets import (
    QSpinBox,
    QStyle,
    QStyleOption,
    QStyleOptionSpinBox,
    QWidget,
)

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class SpinBoxDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def _super(self):
        """Return proxy for calling QCommonStyle methods on style_inst."""
        from ..style import AYONStyle as _AYONStyle

        return super(_AYONStyle, self.style_inst)

    @property
    def base_class(self):
        return {"QSpinBox": QSpinBox}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_SpinBox,
                "QSpinBox",
            ): self.draw_spinbox,
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_SpinBox,
                "QSpinBox",
            ): self.draw_spinbox,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_SpinBox,
                "QSpinBox",
            ): self.sub_control_rect,
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_SpinBox,
                "QSpinBox",
            ): self.sub_control_rect,
        }

    def sub_control_rect(
        self,
        cc: QStyle.ComplexControl,
        opt: QStyleOptionSpinBox,
        sc: QStyle.SubControl,
        w: QWidget | None = None,
    ):
        output = self._super.subControlRect(
            cc, opt, sc, w
        )
        if sc in (
            QStyle.SubControl.SC_SpinBoxUp,
            QStyle.SubControl.SC_SpinBoxDown,
        ):
            output.setLeft(output.right() - (output.height() + 1))
        return output

    def draw_spinbox(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        from ayon_core.ui.components import AYSpinBox

        if isinstance(widget, AYSpinBox):
            return

        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)
        self._super.drawComplexControl(
            QStyle.ComplexControl.CC_SpinBox, option, painter, widget
        )
