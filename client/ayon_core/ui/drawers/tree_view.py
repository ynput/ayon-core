"""TreeViewDrawer: branch indicators and indentation for QTreeView."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QRect, QSize, Qt
from qtpy.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from qtpy.QtWidgets import QStyle, QStyleOption, QTreeView, QWidget

from ._utils import enum_to_str, get_icon

if TYPE_CHECKING:
    from ..style import AYONStyle


class TreeViewDrawer:
    """AYONStyle drawer for QTreeView.

    Handles branch expand/collapse indicators and the indentation metric
    using colours from the QTreeView style data in ayon_style.json.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._icon_cache = {}

    @property
    def base_class(self):
        return {"QTreeView": QTreeView}

    def register_drawers(self) -> dict:
        """Register drawing functions for QTreeView primitives."""
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorBranch,
                "QTreeView",
            ): self.draw_branch_indicator,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelScrollAreaCorner,
                "QTreeView",
            ): self.draw_scrollbar_corner,
        }

    def register_metrics(self) -> dict:
        """Register pixel metric functions for QTreeView."""
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_TreeViewIndentation,
                "QTreeView",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Return indent width from style data.

        Args:
            metric: The pixel metric being queried.
            opt: Optional style option.
            widget: The target widget.

        Returns:
            The indent size in pixels.
        """
        if metric == QStyle.PixelMetric.PM_TreeViewIndentation:
            variant = getattr(widget, "_variant_str", "default")
            style = self.model.get_style("QTreeView", variant)
            return int(style.get("indent", 20))
        return 0

    def _draw_cell_border(
        self,
        painter: QPainter,
        rect: QRect,
        style: dict,
    ) -> None:
        """Draw top and bottom border lines for an AYTableView cell."""
        painter.setPen(
            QPen(
                QColor(style.get("border-color")), style.get("border-width", 1)
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLines(
            [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight(),
            ]
        )

    def _resolve_tree_view(self, widget: QWidget | None) -> QWidget | None:
        """Resolve widget to the actual QTreeView/AYTableView."""
        if widget is not None and not isinstance(widget, QTreeView):
            return widget.parent() or widget
        return widget

    def _paint_cell_background(
        self,
        painter: QPainter,
        rect: QRect,
        style: dict,
        is_table: bool,
        is_base_state: bool = False,
    ) -> None:
        """Paint background fill and optional cell borders.

        Args:
            painter: The QPainter to draw on.
            rect: The rectangle to fill.
            style: The style data dictionary.
            is_table: Whether this is an AYTableView cell.
            is_base_state: If True and is_table, use 'background-color-item'.
        """
        painter.save()
        if is_table and is_base_state:
            bg_key = "background-color-item"
        else:
            bg_key = "background-color"
        painter.fillRect(rect, QColor(style.get(bg_key, "transparent")))
        if is_table:
            self._draw_cell_border(painter, rect, style)
        painter.restore()

    def _paint_icon(
        self,
        painter: QPainter,
        rect: QRect,
        icon,
        icon_size: int | None,
    ) -> None:
        """Paint a cached icon, optionally resizing and repositioning it."""
        draw_rect = QRect(rect)
        if icon_size is not None:
            center = rect.center()
            draw_rect.setSize(QSize(icon_size, icon_size))
            draw_rect.moveTo(
                rect.right() - icon_size, center.y() - icon_size // 2
            )
        icon.paint(painter, draw_rect)

    def _paint_fallback_arrow(
        self,
        painter: QPainter,
        rect: QRect,
        color: QColor,
        is_open: bool,
    ) -> None:
        """Paint a geometric triangle arrow when no icon is configured."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        cx, cy = rect.center().x(), rect.center().y()
        size = max(4, min(rect.width(), rect.height()) // 3)

        path = QPainterPath()
        if is_open:
            path.moveTo(cx - size, cy - size // 2)
            path.lineTo(cx + size, cy - size // 2)
            path.lineTo(cx, cy + size // 2)
        else:
            path.moveTo(cx - size // 2, cy - size)
            path.lineTo(cx - size // 2, cy + size)
            path.lineTo(cx + size // 2, cy)
        path.closeSubpath()
        painter.drawPath(path)

    def draw_branch_indicator(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw expand / collapse arrows for tree branch items.

        Args:
            option: The primitive element style option.
            painter: The QPainter to draw on.
            widget: The QTreeView widget (may be the viewport).
        """
        has_children = bool(option.state & QStyle.StateFlag.State_Children)
        tv = self._resolve_tree_view(widget)
        is_table = type(tv).__name__ == "AYTableView"
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        variant = getattr(tv, "_variant_str", "default")

        state_name = (
            "selected" if is_selected else "hover" if is_hovered else "base"
        )

        widget_class = "AYTableView" if is_table else "QTreeView"
        t_style = self.model.get_style(
            widget_class, variant=variant, state=state_name
        )

        # Items without children only need background/border painting
        if not has_children:
            self._paint_cell_background(
                painter,
                option.rect,
                t_style,
                is_table,
                is_base_state=(state_name == "base"),
            )
            return

        is_open = bool(option.state & QStyle.StateFlag.State_Open)
        color = QColor(t_style.get("branch-indicator-color", "#8b9198"))
        icon_name = t_style.get(
            "expanded-icon-name" if is_open else "expand-icon-name"
        )

        # Paint background for items with children
        self._paint_cell_background(painter, option.rect, t_style, is_table)

        if icon_name:
            key = f"{icon_name}-{color.name()}"
            if key not in self._icon_cache:
                self._icon_cache[key] = get_icon(icon_name, color=color)
            icon_size = t_style.get("expand-icon-size")
            self._paint_icon(
                painter, option.rect, self._icon_cache[key], icon_size
            )
        else:
            self._paint_fallback_arrow(painter, option.rect, color, is_open)

    def draw_scrollbar_corner(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        style = self.model.get_style("QScrollArea", variant="default")
        style.set_context(widget)
        painter.save()
        # Draw corner background
        bg = style.get("background-color", "transparent")
        painter.fillRect(option.rect, QColor(bg))

        painter.restore()
