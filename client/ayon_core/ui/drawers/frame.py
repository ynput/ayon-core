"""FrameDrawer: custom painting for QFrame."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QRectF, Qt
from qtpy.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from qtpy.QtWidgets import QFrame, QStyle, QStyleOption, QWidget

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class FrameDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QFrame": QFrame}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QFrame",
            ): self.draw_frame,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_Widget,
                "QFrame",
            ): self.draw_frame,
        }

    def draw_frame(
        self,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget,
    ):
        # get style
        variant = getattr(w, "_variant_str", "")
        row_state = w.property("row_state") if w is not None else None
        is_selected = bool(row_state and row_state & QStyle.StateFlag.State_Selected)
        is_hover = bool(row_state and row_state & QStyle.StateFlag.State_MouseOver) or (
            getattr(w, "_hover_enabled", False)
            and (
                option.state & QStyle.StateFlag.State_MouseOver
                or w.underMouse()
            )
        )
        if is_selected and is_hover:
            state = "selected-hover"
        elif is_selected:
            state = "selected"
        elif is_hover:
            state = "hover"
        else:
            state = "base"
        style = self.model.get_style("QFrame", variant, state)
        style.set_context(w)

        # widget override for comment types
        border_width = style.get("border-width", 0)
        if hasattr(w, "get_bg_color"):
            bgc: QColor = w.get_bg_color(style["background-color"])
            style = dict(style)
            if border_width == 0:
                style["border-color"] = bgc
            style["background-color"] = bgc
            # set background color of QTextEdit widgets
            if hasattr(w, "viewport"):
                viewport = w.viewport()
                palette = viewport.palette()
                palette.setColor(QPalette.ColorRole.Base, bgc)
                viewport.setPalette(palette)

        # pen setup
        border_color = QColor(style["border-color"])
        pen = QPen(border_color)
        pen.setWidth(border_width)
        if not border_width:
            pen.setStyle(Qt.PenStyle.NoPen)
        elif style.get("border-style", "solid") == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        # brush setup
        bg_color = QColor(style["background-color"])
        brush = QBrush(bg_color)
        radius = style.get("border-radius", 0)
        # draw
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Inset rect by half border width to keep stroke within bounds
        draw_rect = option.rect
        if border_width > 0:
            half_width = border_width / 2.0
            draw_rect = QRectF(option.rect).adjusted(
                half_width, half_width, -half_width, -half_width
            )

        if radius:
            # Clamp to a single value derived from the shorter side so
            # both corner axes stay circular. Qt's own clamping caps
            # each axis independently against half its own dimension,
            # which turns an oversized radius on a wide-but-short rect
            # (e.g. a pill chip) into an ellipse instead of a stadium.
            radius = min(radius, draw_rect.width() / 2.0, draw_rect.height() / 2.0)
            painter.drawRoundedRect(draw_rect, radius, radius)
        else:
            painter.drawRect(draw_rect)
