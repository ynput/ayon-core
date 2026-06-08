"""CheckboxDrawer: custom painting for QCheckBox (toggle switch)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QRect, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPalette, QPen
from qtpy.QtWidgets import QCheckBox, QStyle, QStyleOption, QWidget

from ._utils import do_nothing, enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class CheckboxDrawer:
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
        return {"QCheckBox": QCheckBox}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_CheckBox,
                "QCheckBox",
            ): self.draw_indicator,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                "QCheckBox",
            ): self.draw_toggle,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_FrameFocusRect,
                "QCheckBox",
            ): do_nothing,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_IndicatorWidth,
                "QCheckBox",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_IndicatorHeight,
                "QCheckBox",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing,
                "QCheckBox",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ):
        variant = getattr(widget, "_variant_str", "default")
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
        )
        style.set_context(widget)
        metrics_h = widget.fontMetrics().height() if widget else 18
        metrics_w = metrics_h * 2 if widget else 32

        if metric == QStyle.PixelMetric.PM_IndicatorWidth:
            # if indicator-width == 0, use 2x the font height.
            return style.get("indicator-width", metrics_w) or metrics_w
        elif metric == QStyle.PixelMetric.PM_IndicatorHeight:
            # if indicator-height == 0, use the font height.
            return style.get("indicator-height", metrics_h) or metrics_h
        elif metric == QStyle.PixelMetric.PM_CheckBoxLabelSpacing:
            return style.get("checkbox-label-spacing", 8)
        return 0

    def draw_indicator(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ):
        variant = getattr(widget, "_variant_str", "default")
        state = (
            "checked" if option.state & QStyle.StateFlag.State_On else "base"
        )
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
            state=state,
        )
        style.set_context(widget)

        if style.get("background-color"):
            painter.save()
            painter.setBrush(QColor(style["background-color"]))
            painter.setPen(Qt.PenStyle.NoPen)
            radius = style.get("border-radius", 0)
            painter.drawRoundedRect(option.rect, radius, radius)
            painter.restore()

        if style.get("indicator-position", "left") == "right":
            # Manually draw a centred [label  toggle] group so that padding
            # is equal on both sides, instead of relying on Qt's layout.
            s = self.style_inst
            ind_w = s.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, option, widget
            )
            ind_h = s.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorHeight, option, widget
            )
            spacing = s.pixelMetric(
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, widget
            )

            text = getattr(option, "text", "")
            fm = option.fontMetrics
            text_w = fm.horizontalAdvance(text) if text else 0
            text_h = fm.height()

            total_w = text_w + (spacing + ind_w if text_w else ind_w)

            rect = option.rect
            cx = rect.center().x()
            cy = rect.center().y()
            x = cx - total_w // 2

            painter.save()
            if text:
                painter.setPen(
                    QColor(style["color"])
                    if style.get("color")
                    else option.palette.color(QPalette.ColorRole.WindowText)
                )
                text_rect = QRect(x, cy - text_h // 2, text_w, text_h)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )

            toggle_opt = QStyleOption(option)
            toggle_opt.rect = QRect(
                x + text_w + (spacing if text_w else 0),
                cy - ind_h // 2,
                ind_w,
                ind_h,
            )
            self.draw_toggle(toggle_opt, painter, widget)
            painter.restore()
            return

        if style.get("color"):
            option.palette.setColor(
                QPalette.ColorRole.WindowText, QColor(style["color"])
            )

        self._super.drawControl(
            QStyle.ControlElement.CE_CheckBox, option, painter, widget
        )

    def draw_toggle(
        self,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget | None = None,
    ):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # get style data
        checked = bool(option.state & QStyle.StateFlag.State_On)
        variant = getattr(w, "_variant_str", "default")
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
            state="checked" if checked else "base",
        )
        style.set_context(w)

        # draw toggle background
        painter.setBrush(QColor(style["indicator-background-color"]))
        if style.get("indicator-border-width", 0):
            pen = QPen(QColor(style["indicator-border-color"]))
            pen.setWidth(style.get("indicator-border-width", 0))
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        frame_rect: QRectF = option.rect.toRectF().adjusted(1, 0, -1, 0)
        radius = frame_rect.height() / 2.0
        painter.drawRoundedRect(frame_rect, radius, radius)

        # draw toggle knob
        painter.setBrush(QColor(style["indicator-color"]))
        offset = frame_rect.height() * 0.125
        state_rect: QRectF = frame_rect.adjusted(
            offset, offset, -offset, -offset
        )
        state_rect.setWidth(state_rect.height())
        if checked:
            state_rect.moveRight(frame_rect.right() - offset)
        painter.drawEllipse(state_rect)

        painter.restore()
