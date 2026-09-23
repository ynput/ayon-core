"""ScrollBarDrawer: custom painting for QScrollBar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtWidgets
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import QBrush, QColor, QPainter
from qtpy.QtWidgets import (
    QStyle,
    QStyleOption,
    QStyleOptionComplex,
    QStyleOptionSlider,
    QWidget,
)

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class ScrollBarDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._style = self.model.get_style("QScrollBar")

    @property
    def base_class(self):
        return {"QScrollBar": QtWidgets.QScrollBar}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarSlider,
                "QScrollBar",
            ): self.draw_scrollbar_slider,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarAddPage,
                "QScrollBar",
            ): self.draw_scrollbar_page,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarSubPage,
                "QScrollBar",
            ): self.draw_scrollbar_page,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_ScrollBar,
                "QScrollBar",
            ): self.get_size,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ScrollBarExtent,
                "QScrollBar",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ScrollBarSliderMin,
                "QScrollBar",
            ): self.get_metric,
        }

    def get_size(
        self,
        cc: QStyle.ComplexControl,
        opt: QStyleOptionComplex,
        sc: QStyle.SubControl,
        w: QWidget | None = None,
    ) -> QRect | None:
        """Sub-control rects for a scrollbar without arrow buttons.

        Mirrors QCommonStyle's layout but with the groove spanning the
        whole widget. Painting (QCommonStyle.drawComplexControl) and all
        mouse interaction in QScrollBar (hit testing, dragging, page
        stepping) query these rects, so what is drawn is exactly what
        responds to the mouse.
        """
        if not isinstance(opt, QStyleOptionSlider):
            raise ValueError(f"Unexpected option type: {type(opt)}")

        SC = QStyle.SubControl
        # No arrow buttons: report them as empty so they never get painted
        # nor hit by 'hitTestComplexControl'.
        if sc not in (
            SC.SC_ScrollBarGroove,
            SC.SC_ScrollBarSlider,
            SC.SC_ScrollBarSubPage,
            SC.SC_ScrollBarAddPage,
        ):
            return QRect()

        rect = opt.rect
        horizontal = opt.orientation == Qt.Orientation.Horizontal
        max_len = rect.width() if horizontal else rect.height()

        slider_len = max_len
        if opt.maximum != opt.minimum:
            value_range = opt.maximum - opt.minimum
            slider_len = int(
                opt.pageStep * max_len / (value_range + opt.pageStep)
            )
            slider_min = self.style_inst.pixelMetric(
                QStyle.PixelMetric.PM_ScrollBarSliderMin, opt, w
            )
            slider_len = min(max(slider_len, slider_min), max_len)

        slider_start = QStyle.sliderPositionFromValue(
            opt.minimum,
            opt.maximum,
            opt.sliderPosition,
            max_len - slider_len,
            opt.upsideDown,
        )

        if sc == SC.SC_ScrollBarGroove:
            start, length = 0, max_len
        elif sc == SC.SC_ScrollBarSlider:
            start, length = slider_start, slider_len
        elif sc == SC.SC_ScrollBarSubPage:
            start, length = 0, slider_start
        else:  # SC_ScrollBarAddPage
            start = slider_start + slider_len
            length = max_len - start

        if horizontal:
            ret = QRect(start, 0, length, rect.height())
        else:
            ret = QRect(0, start, rect.width(), length)
        return QStyle.visualRect(opt.direction, rect, ret)

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        self._style.set_context(widget)
        if metric == QStyle.PixelMetric.PM_ScrollBarExtent:
            # Width of a vertical scroll bar and the height of a horizontal
            # scroll bar.
            return int(self._style["width"])
        elif metric == QStyle.PixelMetric.PM_ScrollBarSliderMin:
            # The minimum height of a vertical scroll bar's slider and the
            # minimum width of a horizontal scroll bar's slider.
            return int(self._style["min-length"])
        return 0

    def draw_scrollbar_slider(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the scrollbar slider/thumb."""
        style = self.model.get_style("QScrollBar")
        style.set_context(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw slider background
        rect = option.rect

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(style["background-color"])))
        painter.drawRect(rect)

        radius = style.get("border-radius")
        size = style["slider-width"]
        center = rect.center()
        if option.orientation == Qt.Orientation.Vertical:
            rect.setWidth(size)
        else:
            rect.setHeight(size)
        rect.moveCenter(center)

        radius = min(
            radius, rect.width() / 2, rect.height() / 2
        )
        if option.state & QStyle.StateFlag.State_Sunken:
            slider_color = QColor(style.get("slider-active-color"))
        elif option.activeSubControls & QStyle.SubControl.SC_ScrollBarSlider:
            slider_color = QColor(style.get("slider-hover-color"))
        else:
            slider_color = QColor(style.get("slider-color"))
        painter.setBrush(QBrush(slider_color))
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    def draw_scrollbar_page(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw scrollbar page buttons."""
        style = self.model.get_style("QScrollBar")
        style.set_context(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw slider background
        painter.setBrush(QBrush(QColor(style.get("background-color"))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(option.rect)

        painter.restore()
