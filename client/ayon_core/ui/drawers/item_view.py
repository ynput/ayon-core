"""Item view drawers: ItemViewItemDrawer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import QBrush, QColor, QPainter, QPen
from qtpy.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionViewItem,
    QWidget,
)

from ._utils import enum_to_str, get_icon

if TYPE_CHECKING:
    from ..style import AYONStyle


class ItemViewItemDrawer:
    """Drawer for item view items using QStyledItemDelegate."""

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QStyledItemDelegate": QStyledItemDelegate}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ItemViewItem,
                "QStyledItemDelegate",
            ): self.draw_item_view_item,
        }

    def get_item_view_variant(self, widget: QWidget | None) -> str:
        """Extract item view variant from widget properties."""
        if widget is None:
            return "default"
        if hasattr(widget, "itemDelegate"):
            delegate = widget.itemDelegate()
            if hasattr(delegate, "_variant_str"):
                return delegate._variant_str
        return "default"

    def get_item_view_style(
        self,
        widget: QWidget | None,
        option: QStyleOptionViewItem,
    ) -> tuple[dict, str]:
        """Get the appropriate style dictionary for the widget's variant
        and state.

        Args:
            widget: The parent widget containing the item view.
            option: The style option containing state flags.

        Returns:
            A tuple of (style dictionary, state string).
        """
        variant = self.get_item_view_variant(widget)

        wstate = "base"
        is_checked = option.checkState == Qt.CheckState.Checked
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if is_checked:
            wstate = "checked"
        elif is_hovered:
            wstate = "hover"

        style = self.model.get_style("QStyledItemDelegate", variant, wstate)
        style.set_context(widget)

        return style, wstate

    def draw_item_view_item(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Paint a filter item with checkbox indicator.

        Hover and checked states are handled independently:
        - Background color comes from hover state when hovered
        - Checkbox background and text color come from checked state
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # For QStyleOptionViewItem, we need to check different properties
        if not isinstance(option, QStyleOptionViewItem):
            painter.restore()
            return

        # Determine hover and checked states independently
        is_checked = option.checkState == Qt.CheckState.Checked
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        text = option.text

        # Get variant for style lookups
        variant = self.get_item_view_variant(widget)

        # Get all necessary styles in a single call
        styles = self.model.get_styles(
            "QStyledItemDelegate", variant, ["base", "hover", "checked"]
        )
        base_style = styles["base"]
        hover_style = styles["hover"]
        checked_style = styles["checked"]

        # Constants from base style data
        checkbox_size = base_style.get("checkbox-size", 16)
        checkbox_margin = base_style.get("checkbox-margin", 8)
        text_padding = base_style.get("text-padding", 12)
        border_radius = base_style.get("border-radius", 2)

        # Background: use hover style if hovered, regardless of checked state
        if is_hovered:
            bg_color = QColor(
                hover_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        else:
            bg_color = QColor(
                base_style.get("background-color", "transparent")
            )

        # Text color: use checked style if checked, else base
        if is_checked:
            text_color = QColor(
                checked_style.get("color", base_style.get("color", "#8b9198"))
            )
        else:
            text_color = QColor(base_style.get("color", "#8b9198"))

        # Checkbox background: use checked style if checked, else base
        if is_checked:
            checkbox_bg_color = QColor(
                checked_style.get(
                    "checkbox-background-color",
                    base_style.get("checkbox-background-color", "#424a57"),
                )
            )
        else:
            checkbox_bg_color = QColor(
                base_style.get("checkbox-background-color", "#424a57")
            )

        # Draw background if hovered
        if is_hovered:
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(option.rect)

        # Calculate checkbox rect - positioned on right side
        cb_rect = QRect(
            option.rect.right() - checkbox_size - checkbox_margin,
            option.rect.center().y() - checkbox_size // 2,
            checkbox_size,
            checkbox_size,
        )

        # Draw checkbox background
        painter.setBrush(QBrush(checkbox_bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cb_rect, border_radius, border_radius)

        # Draw X mark if checked
        if is_checked:
            icon = get_icon("close", color="#000000")
            icon_rect = cb_rect.adjusted(2, 2, -2, -2)
            icon.paint(painter, icon_rect)

        # Draw text
        painter.setPen(QPen(text_color))
        text_rect = option.rect.adjusted(
            text_padding,
            0,
            -(checkbox_size + checkbox_margin * 2),
            0,
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

        painter.restore()
