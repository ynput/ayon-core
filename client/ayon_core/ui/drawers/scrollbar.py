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

        if sc == QStyle.SubControl.SC_ScrollBarSlider:
            base_groove = sup.subControlRect(
                cc, opt, QStyle.SubControl.SC_ScrollBarGroove, w
            )
            base_slider = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                groove = base_groove.adjusted(
                    0, -sls.height(), 0, als.height()
                )
                slider_length = base_slider.height()
                available = max(0, groove.height() - slider_length)
                offset = QStyle.sliderPositionFromValue(
                    w.minimum(),
                    w.maximum(),
                    w.sliderPosition(),
                    available,
                    w.invertedAppearance(),
                )
                return QRect(
                    base_slider.left(),
                    groove.top() + offset,
                    base_slider.width(),
                    slider_length,
                )

            groove = base_groove.adjusted(
                -sls.width(), 0, als.width(), 0
            )
            slider_length = base_slider.width()
            available = max(0, groove.width() - slider_length)
            offset = QStyle.sliderPositionFromValue(
                w.minimum(),
                w.maximum(),
                w.sliderPosition(),
                available,
                w.invertedAppearance(),
            )
            return QRect(
                groove.left() + offset,
                base_slider.top(),
                slider_length,
                base_slider.height(),
            )

        if sc == QStyle.SubControl.SC_ScrollBarGroove:
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, -sls.height(), 0, als.height())
            else:
                rect.adjust(-sls.width(), 0, als.width(), 0)
            return rect

        elif sc == QStyle.SubControl.SC_ScrollBarAddPage:
            groove = self.get_size(
                cc, opt, QStyle.SubControl.SC_ScrollBarGroove, w
            )
            slider = self.get_size(
                cc, opt, QStyle.SubControl.SC_ScrollBarSlider, w
            )
            if orientation == Qt.Orientation.Vertical:
                return QRect(
                    groove.left(),
                    slider.bottom() + 1,
                    groove.width(),
                    max(0, groove.bottom() - slider.bottom()),
                )
            return QRect(
                slider.right() + 1,
                groove.top(),
                max(0, groove.right() - slider.right()),
                groove.height(),
            )

        elif sc == QStyle.SubControl.SC_ScrollBarSubPage:
            groove = self.get_size(
                cc, opt, QStyle.SubControl.SC_ScrollBarGroove, w
            )
            slider = self.get_size(
                cc, opt, QStyle.SubControl.SC_ScrollBarSlider, w
            )
            if orientation == Qt.Orientation.Vertical:
                return QRect(
                    groove.left(),
                    groove.top(),
                    groove.width(),
                    max(0, slider.top() - groove.top()),
                )
            return QRect(
                groove.left(),
                groove.top(),
                max(0, slider.left() - groove.left()),
                groove.height(),
            )

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

    def _get_variant_style(self, widget: QWidget | None):
        variant = getattr(widget, "_variant_str", "default")
        style = self.model.get_style("QScrollBar", variant=variant)
        style.set_context(widget)
        return style

    def draw_scrollbar_slider(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the scrollbar slider/thumb.

        Insets the filled rect directly (by half of ``border-width``,
        kept as the inset amount for visual continuity) rather than
        drawing a wide pen in the track's own ``background-color`` —
        that pen doubled as the "padding" between the thumb and the
        scrollbar's own edge, coupling the thumb's look to the track
        always being opaque. A transparent-track variant needs the
        thumb's inset to still work with no track color to borrow.

        The slider's own sub-control rect (``option.rect``) sits
        outside the ``AddPage``/``SubPage`` rects this drawer also
        paints, so the inset margin around the thumb isn't covered by
        either — it must be filled here with the same background-color
        first, or that margin is left to whatever Qt painted underneath
        before this call (opaque black, by default).
        """
        style = self._get_variant_style(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(style.get("background-color"))))
        painter.drawRect(option.rect)

        painter.setBrush(QBrush(QColor(style.get("slider-color"))))
        inset = int(style.get("border-width", 10) / 2)
        rect = option.rect.adjusted(inset, inset, -inset, -inset)
        radius = style.get("border-radius")
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    def draw_scrollbar_page(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw scrollbar page buttons (the track behind the thumb)."""
        style = self._get_variant_style(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(style.get("background-color"))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(option.rect)

        painter.restore()
