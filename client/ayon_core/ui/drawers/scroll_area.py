"""ScrollAreaDrawer: scrollbar corner painting for QScrollArea."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtWidgets
from qtpy.QtGui import QColor, QPainter
from qtpy.QtWidgets import QStyle, QStyleOption, QWidget

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class ScrollAreaDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._style = self.model.get_style("QScrollArea", variant="default")

    @property
    def base_class(self):
        return {"QScrollArea": QtWidgets.QScrollArea}

    def register_drawers(self) -> dict:
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelScrollAreaCorner,
                "QScrollArea",
            ): self.draw_scrollbar_corner,
        }

    def draw_scrollbar_corner(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        self._style.set_context(widget)
        painter.save()
        # Draw corner background
        bg = self._style.get("background-color", "transparent")
        painter.fillRect(option.rect, QColor(bg))

        painter.restore()
