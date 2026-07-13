"""LineEditDrawer: custom painting for QLineEdit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtGui import QPainter
from qtpy.QtWidgets import QLineEdit, QStyle, QStyleOption, QWidget

from ._utils import enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class LineEditDrawer:
    """AYONStyle drawer for QLineEdit.

    Registers a no-op for PE_PanelLineEdit when the widget is an AYLineEdit
    instance (which paints itself fully in its own paintEvent), and falls back
    to the base QCommonStyle implementation for all other QLineEdit widgets.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst

    @property
    def _super(self):
        """Return proxy for calling QCommonStyle methods on style_inst."""
        from ..style import AYONStyle as _AYONStyle

        return super(_AYONStyle, self.style_inst)

    @property
    def base_class(self):
        return {"QLineEdit": QLineEdit}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelLineEdit,
                "QLineEdit",
            ): self.draw_panel,
        }

    def draw_panel(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        # AYLineEdit paints its own background — skip Qt's default frame.
        if type(widget).__name__ == "AYLineEdit":
            return
        self._super.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelLineEdit, option, painter, widget
        )
