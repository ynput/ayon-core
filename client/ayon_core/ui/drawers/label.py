"""LabelDrawer: suppress default frame painting for QLabel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QLabel, QStyle

from ._utils import do_nothing, enum_to_str

if TYPE_CHECKING:
    from ..style import AYONStyle


class LabelDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QLabel": QLabel}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QLabel",
            ): do_nothing,
        }
