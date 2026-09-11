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


def _get_slider_option(
    option: QStyleOptionComplex,
    widget: QtWidgets.QScrollBar,
) -> QStyleOptionSlider:
    """Return a complete slider option across Qt binding versions.

    Older PySide versions may slice a ``QStyleOptionSlider`` to its
    ``QStyleOptionComplex`` base when it passes through a Python style
    override. Reinitializing the concrete option restores range and
    position attributes required for scrollbar geometry.
    """
    required = ("minimum", "maximum", "sliderPosition", "upsideDown")
    if all(hasattr(option, attr) for attr in required):
        return option  # type: ignore[return-value]

    slider_option = QStyleOptionSlider()
    widget.initStyleOption(slider_option)
    return slider_option


class ScrollBarDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._style = self.model.get_style("QScrollBar")
        self._cache = {}

    @property
    def _super(self):
        """Return proxy for calling QCommonStyle methods on style_inst."""
        from ..style import AYONStyle as _AYONStyle

        return super(_AYONStyle, self.style_inst)

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
        if not w:
            raise ValueError(
                "Widget required to calculate scrollbar sub-control rects"
            )

        if not isinstance(opt, QStyleOptionComplex):
            raise ValueError(f"Unexpected option type: {type(opt)}")
        opt = _get_slider_option(opt, w)

        sup = self._super
        try:
            als = self._cache["add_line_size"]
        except KeyError:
            als = self._cache["add_line_size"] = sup.subControlRect(
                cc, opt, QStyle.SubControl.SC_ScrollBarAddLine, w
            ).size()
        try:
            sls = self._cache["sub_line_size"]
        except KeyError:
            sls = self._cache["sub_line_size"] = sup.subControlRect(
                cc, opt, QStyle.SubControl.SC_ScrollBarSubLine, w
            ).size()

        orientation = w.orientation()

        if sc in (
            QStyle.SubControl.SC_ScrollBarSlider,
            QStyle.SubControl.SC_ScrollBarGroove,
        ):
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, -sls.height(), 0, als.height())
            else:
                rect.adjust(-sls.width(), 0, als.width(), 0)
            return rect

        elif sc == QStyle.SubControl.SC_ScrollBarAddPage:
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, 0, 0, als.height())
            else:
                rect.adjust(0, 0, als.width(), 0)
            return rect

        elif sc == QStyle.SubControl.SC_ScrollBarSubPage:
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, -sls.height(), 0, 0)
            else:
                rect.adjust(-sls.width(), 0, 0, 0)
            return rect

        raise ValueError("Unexpected sub-control")

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
