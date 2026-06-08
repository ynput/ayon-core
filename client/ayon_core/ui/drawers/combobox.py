"""ComboBox drawers: ComboBoxDrawer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy import QtCore, QtWidgets
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import QBrush, QColor, QIcon, QPainter, QPalette
from qtpy.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOption,
    QStyleOptionComboBox,
    QWidget,
)

from ._utils import do_nothing, enum_to_str, get_icon

if TYPE_CHECKING:
    from ..style import AYONStyle


class ComboBoxDrawer:
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
        return {"QComboBox": QComboBox}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ComboBoxLabel,
                "QComboBox",
            ): self.draw_label,
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_ComboBox,
                "QComboBox",
            ): self.draw_box,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelItemViewItem,
                "QFrame",
            ): self.draw_panel_item_view_item,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_FrameFocusRect,
                "QFrame",
            ): do_nothing,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ContentsType,
                QStyle.ContentsType.CT_ComboBox,
                "QComboBox",
            ): self.combobox_size,
        }

    def get_fg_bg_colors(
        self,
        opt: QtWidgets.QStyleOptionComplex,
        w: QComboBox,
    ) -> tuple[QColor, QColor]:
        bg_color = opt.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Base
        )
        fg_color = opt.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText
        )

        inverted = getattr(w, "_inverted", False)
        current_index = w.currentIndex()
        if current_index >= 0:
            item_color = w.itemData(
                current_index, QtCore.Qt.ItemDataRole.ForegroundRole
            )
            if item_color is not None:
                item_color = item_color.color()
                fg_color = bg_color if inverted else item_color
                bg_color = item_color if inverted else bg_color

        return fg_color, bg_color

    def draw_box(
        self,
        opt: QtWidgets.QStyleOptionComplex,
        p: QPainter,
        w: QComboBox | None = None,
    ):
        if not isinstance(w, QComboBox):
            return

        _style = self.model.get_style(
            "QComboBox", variant=getattr(w, "_variant_str", None)
        )
        _style.set_context(w)
        style_bg_color = _style.get("background-color", None)
        opt.palette.setBrush(
            QPalette.ColorRole.Base,
            QColor(style_bg_color)
            if style_bg_color
            else self.model.base_palette.base(),
        )
        _radius = _style.get("border-radius", 0)

        if not w.isEditable():
            fg_color, bg_color = self.get_fg_bg_colors(opt, w)

            # Paint background with status color
            rect = opt.rect
            p.save()
            p.setBrush(QBrush(bg_color))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, _radius, _radius)
            p.restore()

            # Draw expand_more arrow if show_chevron is True
            show_chevron = getattr(w, "show_chevron", True)
            if show_chevron:
                arrow_rect = self._super.subControlRect(
                    QStyle.ComplexControl.CC_ComboBox,
                    opt,
                    QStyle.SubControl.SC_ComboBoxArrow,
                    w,
                )
                arrow_icon = get_icon("expand_more", fg_color)
                if arrow_icon and not arrow_rect.isEmpty():
                    arrow_size = min(arrow_rect.width(), arrow_rect.height())
                    pixmap = arrow_icon.pixmap(arrow_size, arrow_size)
                    px = (
                        arrow_rect.x() + (arrow_rect.width() - arrow_size) // 2
                    )
                    py = (
                        arrow_rect.y()
                        + (arrow_rect.height() - arrow_size) // 2
                    )
                    popup_open = bool(opt.state & QStyle.StateFlag.State_On)
                    if popup_open:
                        cx = px + arrow_size / 2
                        cy = py + arrow_size / 2
                        p.save()
                        p.translate(cx, cy)
                        p.rotate(180)
                        p.translate(-cx, -cy)
                        p.drawPixmap(px, py, pixmap)
                        p.restore()
                    else:
                        p.drawPixmap(px, py, pixmap)

            # set pen for text drawing
            p.setPen(fg_color)
        else:
            # editable combobox - IMPLEMENT ME
            self._super.drawComplexControl(
                QStyle.ComplexControl.CC_ComboBox, opt, p, w
            )

    def draw_label(
        self,
        opt: QStyleOptionComboBox,
        p: QPainter,
        w: QWidget,
    ):
        if not isinstance(w, QComboBox):
            return

        _style = self.model.get_style(
            "QComboBox", variant=getattr(w, "_variant_str", None)
        )
        _style.set_context(w)
        icon_padding = _style.get("icon-padding", [4, 4])
        text_padding = _style.get("text-padding", [1, 1])

        fg_color, bg_color = self.get_fg_bg_colors(opt, w)

        base_cls = self._super
        edit_rect = base_cls.subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            opt,
            QStyle.SubControl.SC_ComboBoxEditField,
            w,
        )
        p.save()
        p.setClipRect(edit_rect)
        if opt.currentIcon:
            mode = (
                QIcon.Mode.Normal
                if opt.state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            pixmap = opt.currentIcon.pixmap(opt.iconSize, mode)
            icon_rect = QRect(edit_rect)
            icon_rect.setWidth(opt.iconSize.width() + icon_padding[0])
            icon_rect.setHeight(opt.iconSize.height() + icon_padding[1])
            icon_rect = QStyle.alignedRect(
                opt.direction,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                icon_rect.size(),
                edit_rect,
            )
            if opt.editable:
                p.fillRect(
                    icon_rect, opt.palette.brush(QPalette.ColorRole.Base)
                )
            base_cls.drawItemPixmap(
                p, icon_rect, Qt.AlignmentFlag.AlignCenter, pixmap
            )
            if opt.direction == Qt.LayoutDirection.RightToLeft:
                edit_rect.translate(-icon_padding[0] - opt.iconSize.width(), 0)
            else:
                edit_rect.translate(opt.iconSize.width() + icon_padding[0], 0)

        if opt.currentText and not opt.editable:
            base_cls.drawItemText(
                p,
                edit_rect.adjusted(
                    text_padding[0],
                    -text_padding[1],
                    -text_padding[0],
                    text_padding[1],
                ),
                QStyle.visualAlignment(
                    opt.direction,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
                opt.palette,
                bool(opt.state & QStyle.StateFlag.State_Enabled),
                opt.currentText,
            )

        p.restore()

    def draw_panel_item_view_item(
        self, option: QStyleOption, painter: QPainter, w: QWidget
    ):
        cb = w.model().parent()
        if cb and getattr(cb, "_inverted", False):
            idx = option.index
            if idx:
                fgc = (
                    w.model().data(idx, Qt.ItemDataRole.ForegroundRole).color()
                )
                option.backgroundBrush.setColor(fgc)
        else:
            stl = self.model.get_style("QComboBox")
            stl.set_context(w)
            option.backgroundBrush.setColor(
                QColor(stl["menu-background-color"])
            )
        self._super.drawPrimitive(  # type: ignore
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w
        )

    def combobox_size(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QtCore.QSize,
        widget: QWidget | None,
    ) -> QtCore.QSize:
        from qtpy.QtCore import QSize

        if not option or not isinstance(option, QStyleOptionComboBox):
            return QSize()

        style = self.model.get_style("QComboBox")
        style.set_context(widget)

        text_width = cb_height = 0
        if isinstance(widget, QComboBox):
            for i in range(widget.count()):
                t_rect = option.fontMetrics.boundingRect(
                    widget.itemData(i, Qt.ItemDataRole.DisplayRole)
                )
                text_width = max(text_width, t_rect.width())
                cb_height = max(cb_height, t_rect.height())

        text_width += style["text-padding"][0] * 2
        cb_height += style["text-padding"][1] * 2

        icon_width = 0
        if option.currentIcon:
            icon_size = getattr(widget, "_icon_size", 0)
            if icon_size == 0:
                all_sizes = option.currentIcon.availableSizes()
                icon_size = max(all_sizes[0].width(), all_sizes[0].height())
            icon_width = icon_size + style["icon-padding"][0] * 2
            icon_height = icon_size + style["icon-padding"][1] * 2
            cb_height = max(cb_height, icon_height)
            if text_width:
                icon_width += style["text-padding"][0]

        final_size = QSize(
            text_width + icon_width,
            min(getattr(widget, "_height", cb_height), cb_height),
        )
        return final_size
