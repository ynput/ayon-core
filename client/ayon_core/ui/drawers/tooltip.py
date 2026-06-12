"""TooltipDrawer: custom painting for QToolTip."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import QBrush, QPainter, QPen
from qtpy.QtWidgets import (
    QFrame,
    QStyle,
    QStyleOption,
    QStyleOptionFrame,
    QToolTip,
    QWidget,
)

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class TooltipDrawer:
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
        return {"QToolTip": QToolTip}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QToolTip",
            ): self.draw_control,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelTipLabel,
                "QToolTip",
            ): partial(
                self.draw_primitive, QStyle.PrimitiveElement.PE_PanelTipLabel
            ),
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_Frame,
                "QToolTip",
            ): partial(self.draw_primitive, QStyle.PrimitiveElement.PE_Frame),
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_ShapedFrameContents,
                "QToolTip",
            ): self.get_rect,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_FrameLayoutItem,
                "QToolTip",
            ): self.get_rect,
        }

    def draw_control(
        self,
        option: QStyleOptionFrame,
        painter: QPainter,
        widget: QWidget,
    ):
        option.frameShadow = QFrame.Shadow.Plain
        option.frameShape = QFrame.Shape.StyledPanel
        self._super.drawControl(
            QStyle.ControlElement.CE_ShapedFrame, option, painter, widget
        )

    def draw_primitive(
        self,
        prim: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget,
    ) -> None:
        if prim == QStyle.PrimitiveElement.PE_Frame:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            style = self.model.get_style("QToolTip")
            style.set_context(w)
            pen = QPen(style["border-color"])
            pen.setWidth(style["border-width"])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            radius = int(style["border-radius"])
            painter.drawRoundedRect(
                option.rect,
                radius,
                radius,
            )
            painter.restore()

        elif prim == QStyle.PrimitiveElement.PE_PanelTipLabel:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            style = self.model.get_style("QToolTip")
            style.set_context(w)
            brush = QBrush(style["background-color"])
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = int(style["border-radius"])
            painter.drawRoundedRect(
                option.rect,
                radius,
                radius,
            )
            painter.restore()

    def get_rect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget,
    ) -> QRect:
        tt_style = self.model.get_style("QToolTip")
        tt_style.set_context(widget)
        tt_pad_x, tt_pad_y = tt_style["padding"]

        if element == QStyle.SubElement.SE_ShapedFrameContents:
            if isinstance(option, QStyleOptionFrame):
                option.features = QStyleOptionFrame.FrameFeature.Rounded
                option.frameShape = QFrame.Shape.StyledPanel
                widget.setContentsMargins(
                    tt_pad_x, tt_pad_y, tt_pad_x, tt_pad_y
                )

        elif element == QStyle.SubElement.SE_FrameLayoutItem:
            if isinstance(option, QStyleOptionFrame):
                option.features = QStyleOptionFrame.FrameFeature.Rounded
                option.frameShape = QFrame.Shape.StyledPanel
                widget.setContentsMargins(
                    tt_pad_x, tt_pad_y, tt_pad_x, tt_pad_y
                )

        return self._super.subElementRect(element, option, widget)
