"""TableHeaderDrawer: custom painting for QHeaderView."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from qtpy import QtWidgets
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen
from qtpy.QtWidgets import QStyle, QStyleOption, QWidget

from ._utils import enum_to_str, get_icon

if TYPE_CHECKING:
    from ..style import AYONStyle


class TableHeaderDrawer:
    """AYONStyle drawer for QHeaderView used by AYTableView.

    Handles painting of header sections and labels using colours
    from the AYTableView style data in ayon_style.json.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._icon_cache: dict[str, QIcon] = {}

    @property
    def base_class(self):
        return {"QHeaderView": QtWidgets.QHeaderView}

    def register_drawers(self) -> dict:
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_Header,
                "QHeaderView",
            ): [
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_HeaderSection,
                ),
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_HeaderLabel,
                ),
            ],
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_HeaderSection,
                "QHeaderView",
            ): self.draw_header_section,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_HeaderLabel,
                "QHeaderView",
            ): self.draw_header_label,
        }

    def register_metrics(self) -> dict:
        """Register pixel metrics for QHeaderView."""
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_HeaderMargin,
                "QHeaderView",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Return header margin from style data."""
        if metric == QStyle.PixelMetric.PM_HeaderMargin:
            return 4
        return 0

    def _get_table_style(self, widget: QWidget | None) -> dict:
        """Resolve the AYTableView style for the header's parent table."""
        variant = "default"
        if widget is not None:
            # QHeaderView's parent is the QTreeView/AYTableView
            table = widget.parent()
            if table is not None:
                variant = getattr(table, "_variant_str", "default")
        return self.model.get_style("AYTableView", variant)

    def draw_header_section(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the header section background and bottom border."""
        style = self._get_table_style(widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background
        bg_color = QColor(style.get("header-background-color", "#272d35"))
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(option.rect)

        # Bottom border
        border_color = QColor(style.get("header-border-color", "#41474d"))
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)
        bottom = option.rect.bottom()
        painter.drawLine(
            option.rect.left(),
            bottom,
            option.rect.right(),
            bottom,
        )

        painter.restore()

    def draw_header_label(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the header label text and sort indicator."""
        style = self._get_table_style(widget)
        padding = style.get("header-padding", [4, 8])

        painter.save()

        # Text
        text_color = QColor(style.get("header-color", "#c1c7ce"))
        painter.setPen(text_color)

        font = painter.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        text_rect = option.rect.adjusted(
            padding[1], padding[0], -padding[1], -padding[0]
        )

        text = ""
        if hasattr(option, "text"):
            text = option.text or ""

        # Check for sort indicator
        sort_indicator = getattr(option, "sortIndicator", None)
        indicator_space = 0
        if sort_indicator and sort_indicator != 0:
            indicator_space = 16

        if text:
            draw_rect = QRect(text_rect)
            if indicator_space:
                draw_rect.setRight(draw_rect.right() - indicator_space)
            painter.drawText(
                draw_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )

        # Sort indicator arrow
        if sort_indicator and sort_indicator != 0:
            indicator_color = QColor(
                style.get(
                    "header-sort-indicator-color",
                    "#8fceff",
                )
            )
            # sortIndicator: 1 = Down, 2 = Up (in QStyleOptionHeader)
            icon_name = (
                "arrow_downward" if sort_indicator == 1 else "arrow_upward"
            )
            cache_key = f"{icon_name}-{indicator_color.name()}"
            if cache_key not in self._icon_cache:
                self._icon_cache[cache_key] = get_icon(
                    icon_name, color=indicator_color
                )
            icon = self._icon_cache[cache_key]
            icon_rect = QRect(
                text_rect.right() - 14,
                text_rect.center().y() - 7,
                14,
                14,
            )
            icon.paint(painter, icon_rect)

        painter.restore()
