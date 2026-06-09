"""MenuDrawer: custom painting for QMenu."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qtpy.QtCore import QRect, QRectF, QSize, Qt
from qtpy.QtGui import QBrush, QColor, QFontMetrics, QIcon, QPainter, QPen
from qtpy.QtWidgets import (
    QMenu,
    QStyle,
    QStyleOption,
    QStyleOptionMenuItem,
    QWidget,
)

from ._utils import do_nothing, enum_to_str, get_icon

if TYPE_CHECKING:
    from ..style import AYONStyle


@dataclass
class MenuItemLayout:
    """Dataclass to hold the results of menu item layout calculations."""

    pad_h: int
    pad_v: int
    icon_size: int
    item_spacing: int
    icon_gutter: int
    label_text: str
    shortcut_text: str
    text_w: int
    text_h: int
    sc_w: int
    arrow_w: int
    row_h: int
    total_w: int


class MenuDrawer:
    """Drawer for QMenu using native QPainter calls (no QSS).

    Paints the menu panel/border (PE_PanelMenu/PE_FrameMenu) and each
    item row (CE_MenuItem).
    """

    _WIDGET_CLS = "QMenu"

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self) -> dict:
        return {"QMenu": QMenu}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_drawers(self) -> dict:
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelMenu,
                "QMenu",
            ): self.draw_panel,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_FrameMenu,
                "QMenu",
            ): self.draw_frame,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_MenuItem,
                "QMenu",
            ): self.draw_menu_item,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_MenuEmptyArea,
                "QMenu",
            ): do_nothing,
        }

    def register_sizers(self) -> dict:
        return {
            enum_to_str(
                QStyle.ContentsType,
                QStyle.ContentsType.CT_MenuItem,
                "QMenu",
            ): self.menu_item_size,
        }

    def register_metrics(self) -> dict:
        pm = QStyle.PixelMetric
        metrics_map = {
            pm.PM_MenuPanelWidth: self.get_metric,
            pm.PM_MenuHMargin: self.get_metric,
            pm.PM_MenuVMargin: self.get_metric,
            pm.PM_SmallIconSize: self.get_metric,
            pm.PM_MenuButtonIndicator: self.get_metric,
        }
        return {enum_to_str(pm, k, "QMenu"): v for k, v in metrics_map.items()}

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _base_style(self, widget: QWidget | None = None):
        """Return the base style dict, context-bound to *widget*."""
        style = self.model.get_style(self._WIDGET_CLS, "default", "base")
        style.set_context(widget)
        return style

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        pm = QStyle.PixelMetric
        style = self._base_style(widget)
        if metric == pm.PM_MenuPanelWidth:
            return int(style.get("border-width", 1))
        if metric in (pm.PM_MenuHMargin, pm.PM_MenuVMargin):
            pp = style.get("panel-padding", [4, 4])
            if isinstance(pp, (list, tuple)):
                return int(pp[0] if metric == pm.PM_MenuHMargin else pp[1])
            return int(pp)
        if metric == pm.PM_SmallIconSize:
            return int(style.get("icon-size", 16))
        if metric == pm.PM_MenuButtonIndicator:
            return int(style.get("icon-size", 16))
        return 0

    # ------------------------------------------------------------------
    # Sizing and Layout Helper
    # ------------------------------------------------------------------

    def _compute_layout(
        self,
        option: QStyleOptionMenuItem,
        style: dict[str, Any],
        contents_size: QSize | None = None,
    ) -> MenuItemLayout:
        """Compute the metrics, dimensions and layouts for a menu item.

        Args:
            option: The style option for the menu item.
            style: The resolved style dict.
            contents_size: Optional contents size passed from size query.

        Returns:
            The computed layout information for the menu item.
        """
        ip = style.get("item-padding", [6, 6])
        if isinstance(ip, (list, tuple)):
            pad_h, pad_v = int(ip[0]), int(ip[1])
        else:
            pad_h = pad_v = int(ip)

        icon_size = int(style.get("icon-size", 16))
        item_spacing = int(style.get("item-spacing", 4))

        fm = option.fontMetrics
        text_h = (
            fm.height()
            if fm
            else (
                contents_size.height()
                if contents_size
                else option.rect.height()
            )
        )
        if text_h <= 0:
            text_h = 16

        row_h = max(text_h + pad_v * 2, icon_size + pad_v * 2)

        text = option.text or ""
        label, _, shortcut = text.partition("\t")
        text_w = (
            fm.horizontalAdvance(label)
            if fm
            else (contents_size.width() if contents_size else 0)
        )

        sc_w = getattr(
            option,
            "reservedShortcutWidth",
            getattr(option, "tabWidth", 0),
        )
        if shortcut and sc_w == 0 and fm:
            sc_w = fm.horizontalAdvance(shortcut)

        icon_gutter = option.maxIconWidth or (icon_size + item_spacing)
        is_submenu = (
            option.menuItemType == QStyleOptionMenuItem.MenuItemType.SubMenu
        )
        arrow_w = icon_size if is_submenu else 0

        total_w = (
            icon_gutter
            + pad_h
            + text_w
            + (pad_h + sc_w if sc_w else 0)
            + (pad_h + arrow_w if arrow_w else 0)
            + pad_h
        )

        return MenuItemLayout(
            pad_h=pad_h,
            pad_v=pad_v,
            icon_size=icon_size,
            item_spacing=item_spacing,
            icon_gutter=icon_gutter,
            label_text=label,
            shortcut_text=shortcut,
            text_w=text_w,
            text_h=text_h,
            sc_w=sc_w,
            arrow_w=arrow_w,
            row_h=row_h,
            total_w=total_w,
        )

    def menu_item_size(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QSize,
        widget: QWidget | None = None,
    ) -> QSize:
        """Compute the bounding size of a single menu item row."""
        if not isinstance(option, QStyleOptionMenuItem):
            return QSize(contents_size.width(), contents_size.height())

        style = self._base_style(widget)

        # Separator: early exit
        sep_type = QStyleOptionMenuItem.MenuItemType.Separator
        if option.menuItemType == sep_type:
            sep_h = int(style.get("separator-height", 1))
            return QSize(contents_size.width(), sep_h)

        layout = self._compute_layout(option, style, contents_size)
        return QSize(
            max(layout.total_w, contents_size.width()),
            layout.row_h,
        )

    # ------------------------------------------------------------------
    # Primitive painting: panel & frame
    # ------------------------------------------------------------------

    def draw_panel(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Fill the menu background with the panel colour."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        style = self._base_style(widget)
        radius = int(style.get("border-radius", 6))
        painter.setBrush(QBrush(QColor(style["background-color"])))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(option.rect, radius, radius)
        painter.restore()

    def draw_frame(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Stroke the menu border."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        style = self._base_style(widget)
        radius = int(style.get("border-radius", 6))
        bw = int(style.get("border-width", 1))
        pen = QPen(QColor(style["border-color"]))
        pen.setWidth(bw)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Inset by half the pen width so the stroke is fully inside the rect.
        inset = bw / 2.0
        inset_rect = QRectF(option.rect).adjusted(inset, inset, -inset, -inset)
        painter.drawRoundedRect(inset_rect, radius, radius)
        painter.restore()

    # ------------------------------------------------------------------
    # Control painting: individual item rows
    # ------------------------------------------------------------------

    def draw_menu_item(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Paint a single QMenu row (normal, separator, submenu)."""
        if not isinstance(option, QStyleOptionMenuItem):
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Handle separators and return
        sep_type = QStyleOptionMenuItem.MenuItemType.Separator
        if option.menuItemType == sep_type:
            self._draw_separator(option, painter, widget)
            painter.restore()
            return

        # Resolve state and fetch styles
        is_enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        state = (
            "hover"
            if is_selected and is_enabled
            else "disabled"
            if not is_enabled
            else "base"
        )

        # Resolve variant from action property, if available
        action = None
        if isinstance(widget, QMenu):
            action = widget.actionAt(option.rect.center())
        variant = (action.property("variant") if action else None) or "default"

        style = self.model.get_style(
            self._WIDGET_CLS, variant=variant, state=state
        )
        style.set_context(widget)

        layout = self._compute_layout(option, style)
        item_radius = int(style.get("item-radius", 4))
        rect = option.rect

        # --- Selection background ---
        bg = QColor(style.get("background-color", "#424a57"))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, item_radius, item_radius)

        opacity = 1.0
        if not is_enabled:
            opacity = float(style.get("opacity", 0.5))
        painter.setOpacity(opacity)

        # --- Left gutter (icon or check mark) ---
        x = rect.left() + layout.pad_h
        cy = rect.center().y()

        check_type = option.checkType
        not_checkable = QStyleOptionMenuItem.CheckType.NotCheckable
        if check_type != not_checkable:
            check_color = QColor(style.get("color", "#f4f5f5"))
            check_icon = get_icon(
                "check_box" if option.checked else "check_box_outline_blank",
                color=check_color,
                fill=False,
            )
            check_rect = QRect(
                x,
                cy - layout.icon_size // 2,
                layout.icon_size,
                layout.icon_size,
            )
            check_icon.paint(painter, check_rect)
        elif not option.icon.isNull():
            icon_rect = QRect(
                x,
                cy - layout.icon_size // 2,
                layout.icon_size,
                layout.icon_size,
            )
            mode = QIcon.Mode.Disabled if not is_enabled else QIcon.Mode.Normal
            option.icon.paint(
                painter, icon_rect, Qt.AlignmentFlag.AlignCenter, mode
            )

        x += layout.icon_gutter

        # --- Text (label + shortcut) ---
        text_color = QColor(style.get("color", "#f4f5f5"))
        painter.setPen(QPen(text_color))

        right_margin = layout.pad_h + (
            layout.arrow_w + layout.pad_h if layout.arrow_w else 0
        )
        label_rect = QRect(
            x,
            rect.top(),
            rect.right()
            - x
            - right_margin
            - (layout.sc_w + layout.pad_h if layout.sc_w else 0),
            rect.height(),
        )
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            layout.label_text,
        )

        if layout.shortcut_text:
            sc_bg_color = QColor(
                style.get(
                    "shortcut-background-color",
                    style.get("background-color", "#2b3036"),
                )
            )
            text_rect = QFontMetrics(
                self.style_inst.model.base_font
            ).boundingRect(layout.shortcut_text)
            painter.setBrush(QBrush(sc_bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            sc_rect = QRect(
                rect.right() - right_margin - layout.sc_w - layout.pad_h,
                rect.top(),
                layout.sc_w + layout.pad_h,
                rect.height(),
            )
            text_rect.moveCenter(sc_rect.center())
            painter.drawRoundedRect(text_rect.adjusted(-4, 0, 4, 0), 4, 4)

            sc_color = QColor(
                style.get(
                    "shortcut-color",
                    style.get("color", "#8b9198"),
                )
            )
            sc_color.setAlphaF(style.get("shortcut-opacity", 0.6))
            painter.setPen(QPen(sc_color))
            painter.drawText(
                sc_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                layout.shortcut_text,
            )

        # --- Submenu arrow ---
        if layout.arrow_w > 0:
            arrow_color = QColor(style.get("color", "#f4f5f5"))
            arrow_icon = get_icon("chevron_right", color=arrow_color)
            arrow_rect = QRect(
                rect.right() - layout.pad_h - layout.arrow_w,
                cy - layout.icon_size // 2,
                layout.icon_size,
                layout.icon_size,
            )
            arrow_icon.paint(painter, arrow_rect)

        painter.restore()

    def _draw_separator(
        self,
        option: QStyleOptionMenuItem,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw a thin horizontal separator line."""
        style = self._base_style(widget)
        color = QColor(
            style.get("separator-color", style.get("border-color", "#41474d"))
        )
        sep_h = int(style.get("separator-height", 1))

        cy = option.rect.center().y()
        y = cy - sep_h // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRect(
            option.rect.left(),
            y,
            option.rect.width(),
            sep_h,
        )
