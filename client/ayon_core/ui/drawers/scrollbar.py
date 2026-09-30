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
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_ScrollBar,
                "QScrollBar",
            ): self.draw_scrollbar,
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
        whole widget. Painting and all mouse interaction (hit testing,
        dragging, page stepping) query these rects, so what is drawn is
        exactly what responds to the mouse.
        """
        opt = self._slider_option(opt, w)
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

    @staticmethod
    def _slider_option(
        opt: QStyleOption, w: QWidget | None
    ) -> QStyleOptionSlider:
        """Return ``opt`` as a QStyleOptionSlider.

        PySide2 does not downcast style options that Qt passes from C++ into
        Python overrides (e.g. from 'hitTestComplexControl'), so they arrive
        as QStyleOptionComplex without the slider fields. Rebuild those from
        the scrollbar widget in that case.
        """
        if isinstance(opt, QStyleOptionSlider):
            return opt
        if not isinstance(w, QtWidgets.QScrollBar):
            raise ValueError(f"Unexpected option type: {type(opt)}")
        slider_opt = QStyleOptionSlider()
        slider_opt.initFrom(w)
        slider_opt.rect = opt.rect
        slider_opt.state = opt.state
        slider_opt.direction = opt.direction
        if isinstance(opt, QStyleOptionComplex):
            slider_opt.subControls = opt.subControls
            slider_opt.activeSubControls = opt.activeSubControls
        slider_opt.orientation = w.orientation()
        slider_opt.minimum = w.minimum()
        slider_opt.maximum = w.maximum()
        slider_opt.sliderPosition = w.sliderPosition()
        slider_opt.sliderValue = w.value()
        slider_opt.singleStep = w.singleStep()
        slider_opt.pageStep = w.pageStep()
        slider_opt.upsideDown = w.invertedAppearance()
        return slider_opt

    def draw_scrollbar(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the scrollbar background and slider."""
        option = self._slider_option(option, widget)
        style = self.model.get_style("QScrollBar")
        style.set_context(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QBrush(QColor(style["background-color"])))
        painter.drawRect(option.rect)

        if not option.subControls & QStyle.SubControl.SC_ScrollBarSlider:
            painter.restore()
            return

        rect = self.get_size(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            widget,
        )
        size = style["slider-width"]
        center = rect.center()
        if option.orientation == Qt.Orientation.Vertical:
            rect.setWidth(size)
        else:
            rect.setHeight(size)
        rect.moveCenter(center)

        radius = min(
            style.get("border-radius"), rect.width() / 2, rect.height() / 2
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
