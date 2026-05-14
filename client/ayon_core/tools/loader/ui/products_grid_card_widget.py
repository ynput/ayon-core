"""Single product card for Loader grid view (web-style layout)."""
from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Any, Optional

import qtawesome
from qtpy import QtCore, QtGui, QtWidgets

import ayon_api
from ayon_core.style import get_default_entity_icon_color, get_objected_colors

from .products_delegates import VersionComboBox
from .products_model import (
    PRODUCT_ID_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_ID_ROLE,
)
from .actions_utils import (
    _maybe_arm_drag_precache,
    loader_drag_start_distance,
    run_loader_drag_for_card,
)

# Thumbnail plate canvas aspect only; title/chrome sit above and add to tile height.
THUMB_REF_WIDTH = 16
THUMB_REF_HEIGHT = 9

# Layout design width (scaling reference for margins / header / overlays).
CARD_BASE_WIDTH = 168
CARD_H_PADDING = 2
CARD_V_PADDING = 2
HEADER_BASE_H = 16
ROOT_LAYOUT_SPACING = 1
# Title/header layout padding in pixels.
CARD_TITLE_PADDING = 1
THUMB_INNER_W = CARD_BASE_WIDTH - 2 * CARD_H_PADDING
# Minimum thumb height so version/review overlays fit at tiny sizes.
MIN_THUMB_HEIGHT_PX = 28
GRID_VERSION_POPUP_MIN_WIDTH_PX = 60
GRID_VERSION_FONT_MAX_PT = 10
GRID_VERSION_FONT_MIN_PT = 8


def layout_dims_for_cell_width(cell_w: int) -> dict:
    """Shared chrome + thumb vertical math for a given cell (tile) width in pixels."""
    tw = max(4, int(cell_w))
    scale = max(0.18, tw / float(CARD_BASE_WIDTH))
    h_pad = CARD_H_PADDING
    v_pad_top = CARD_V_PADDING
    v_pad_bot = CARD_V_PADDING
    g = ROOT_LAYOUT_SPACING
    iz = max(10, int(round(13 * scale)))
    hdr_h = max(iz, int(round(HEADER_BASE_H * scale)))
    strip_pad = CARD_TITLE_PADDING
    row_inner = max(iz, hdr_h)
    header_outer_h = row_inner + 2 * strip_pad
    inner_w = max(1, tw - 2 * h_pad)
    thumb_h = int(
        round(inner_w * float(THUMB_REF_HEIGHT) / float(THUMB_REF_WIDTH))
    )
    thumb_h = max(MIN_THUMB_HEIGHT_PX, thumb_h)
    tile_h = v_pad_top + header_outer_h + g + thumb_h + v_pad_bot
    return {
        "tw": tw,
        "scale": scale,
        "h_pad": h_pad,
        "v_pad_top": v_pad_top,
        "v_pad_bot": v_pad_bot,
        "g": g,
        "iz": iz,
        "hdr_h": hdr_h,
        "strip_pad": strip_pad,
        "header_outer_h": header_outer_h,
        "inner_w": inner_w,
        "thumb_h": thumb_h,
        "tile_h": tile_h,
    }


def tile_size_for_cell_width(cell_w: int) -> QtCore.QSize:
    """List item / card size: width × (title chrome + thumb at THUMB_REF aspect)."""
    d = layout_dims_for_cell_width(cell_w)
    return QtCore.QSize(d["tw"], d["tile_h"])


CARD_BASE_HEIGHT = tile_size_for_cell_width(CARD_BASE_WIDTH).height()
# Rounded thumb plate (match reference; slightly inside card CSS radius).
THUMB_CORNER_RADIUS = 9.0
# Selection ring painted by ProductsGridCardWidget at the actual index-widget geometry.
GRID_CARD_OUTLINE_RADIUS_PX = 11.0
GRID_CARD_SELECTION_WIDTH_PX = 3
GRID_CARD_SELECTION_HEX = "#8fceff"
GRID_CARD_HOVER_HEX = "#6eb8e0"
PLACEHOLDER_ICON_SIZE_RATIO = 0.30
# Empty thumbnail plate (AYON web grid); not theme bg-view.
THUMB_EMPTY_PLATE_HEX = "#272d35"


def _open_external_icon(icon_color: str) -> QtGui.QIcon:
    """Icon for 'open in browser'; Material Symbols names are not in all qtawesome builds."""
    for spec in ("fa.external-link", "fa5s.external-link-alt"):
        try:
            return qtawesome.icon(spec, color=icon_color)
        except Exception:
            continue
    return QtGui.QIcon()


class _ThumbPaintWidget(QtWidgets.QWidget):
    """Rounded thumbnail plate; opaque overlays receive their own mouse."""

    def __init__(self, card: "ProductsGridCardWidget"):
        super().__init__(card)
        self._card = card
        self.setMouseTracking(False)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        path = QtGui.QPainterPath()
        r = self._card.thumb_corner_radius_px()
        path.addRoundedRect(
            QtCore.QRectF(rect),
            r,
            r,
            QtCore.Qt.SizeMode.AbsoluteSize,
        )
        border = get_objected_colors("border").get_qcolor()
        painter.fillPath(path, QtGui.QColor(THUMB_EMPTY_PLATE_HEX))

        version_id = self._card.version_id
        thumb_path = (
            self._card._grid.get_thumbnail_path(version_id) if version_id else None
        )
        icon = self._card.product_icon
        pixmap: Optional[QtGui.QPixmap] = None
        if thumb_path:
            pm = QtGui.QPixmap(thumb_path)
            if not pm.isNull():
                pixmap = pm

        inner = rect.adjusted(1, 1, -1, -1)
        inner_path = QtGui.QPainterPath()
        ir = max(0.0, r - 1.0)
        inner_path.addRoundedRect(
            QtCore.QRectF(inner),
            ir,
            ir,
            QtCore.Qt.SizeMode.AbsoluteSize,
        )
        painter.setClipPath(inner_path)

        if pixmap is not None:
            scaled = pixmap.scaled(
                inner.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            draw = QtCore.QRect(0, 0, scaled.width(), scaled.height())
            draw.moveCenter(inner.center())
            painter.drawPixmap(draw, scaled)
        else:
            if icon and not icon.isNull():
                size = int(
                    min(inner.width(), inner.height()) * PLACEHOLDER_ICON_SIZE_RATIO
                )
                size = max(size, 16)
                ip = icon.pixmap(QtCore.QSize(size, size))
                x = inner.x() + (inner.width() - ip.width()) // 2
                y = inner.y() + (inner.height() - ip.height()) // 2
                painter.drawPixmap(x, y, ip)

        painter.setClipping(False)
        pen = QtGui.QPen(border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class ProductsGridCardWidget(QtWidgets.QWidget):
    """Title/header strip + thumbnail plate (THUMB_REF aspect) + overlays; tile height from layout_dims."""

    def __init__(self, grid: Any, flat_row: int, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ProductsGridCard")
        self.setAutoFillBackground(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._grid = grid
        self._section: Any = grid
        self._flat_row = flat_row
        self._drag_start_pos: Optional[QtCore.QPoint] = None
        self._card_grid_interaction = False

        self._icon_label = QtWidgets.QLabel(self)
        self._icon_label.setObjectName("ProductsGridCardIcon")
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setScaledContents(True)
        self._icon_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        self._name_label = QtWidgets.QLabel(self)
        self._name_label.setObjectName("ProductsGridCardTitle")
        # Qt 5: QLabel has setElideMode. Qt 6 / PySide6: elide via QFontMetrics in
        # _apply_name_label_text + resizeEvent.
        if hasattr(self._name_label, "setElideMode"):
            self._name_label.setElideMode(QtCore.Qt.TextElideMode.ElideRight)
        else:
            self._name_label.setWordWrap(False)
        self._name_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._full_product_name = ""

        self._header_layout = QtWidgets.QHBoxLayout()
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(6)
        self._header_layout.addWidget(self._icon_label, 0)
        self._header_layout.addWidget(self._name_label, 1)

        self._thumb = _ThumbPaintWidget(self)
        self._thumb.setObjectName("ProductsGridCardThumb")
        self._thumb.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        # Overlays on the thumb (local coords; clip to plate with siblings above paint).
        self._version_combo: Optional[VersionComboBox] = None
        self._review_btn = QtWidgets.QToolButton(self._thumb)
        self._review_btn.setObjectName("ProductsGridReviewButton")
        self._review_btn.installEventFilter(self)
        self._review_btn.setAutoRaise(False)
        self._review_btn.setToolTip("Open in AYON (version / activity)")
        self._review_btn.clicked.connect(self._on_review_clicked)

        self._root_layout = QtWidgets.QVBoxLayout(self)
        self._root_layout.setContentsMargins(
            CARD_H_PADDING,
            CARD_V_PADDING,
            CARD_H_PADDING,
            CARD_V_PADDING,
        )
        self._root_layout.setSpacing(ROOT_LAYOUT_SPACING)
        self._root_layout.addLayout(self._header_layout, 0)
        self._root_layout.addWidget(self._thumb, 0)

        self.product_icon: Optional[QtGui.QIcon] = None
        self.version_id: Optional[str] = None
        self._product_id: Optional[str] = None

    @property
    def version_combo(self) -> Optional[VersionComboBox]:
        return self._version_combo

    def thumb_corner_radius_px(self) -> float:
        tw = self.width()
        if tw <= 0:
            return THUMB_CORNER_RADIUS
        return max(3.0, THUMB_CORNER_RADIUS * tw / float(CARD_BASE_WIDTH))

    def set_grid_row_selected(self, selected: bool) -> None:
        """Header strip accent follows list selection (QSS reads dynamic property)."""
        self.setProperty("gridSelected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.property("gridSelected"):
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(GRID_CARD_SELECTION_HEX))
        pen.setWidth(GRID_CARD_SELECTION_WIDTH_PX)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        inset = GRID_CARD_SELECTION_WIDTH_PX * 0.5
        rect = QtCore.QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.drawRoundedRect(
            rect,
            GRID_CARD_OUTLINE_RADIUS_PX,
            GRID_CARD_OUTLINE_RADIUS_PX,
        )

    def _sync_scaled_chrome(self) -> None:
        tw = self.width()
        if tw < 4:
            return
        d = layout_dims_for_cell_width(tw)
        self._root_layout.setContentsMargins(
            d["h_pad"], d["v_pad_top"], d["h_pad"], d["v_pad_bot"]
        )
        self._root_layout.setSpacing(d["g"])
        iz = d["iz"]
        self._icon_label.setFixedSize(iz, iz)
        scale = d["scale"]
        self._header_layout.setSpacing(max(2, int(round(6 * scale))))
        self._name_label.setMinimumHeight(d["hdr_h"])
        strip_pad = d["strip_pad"]
        self._header_layout.setContentsMargins(
            strip_pad, strip_pad, strip_pad, strip_pad
        )
        self._thumb.setFixedHeight(int(d["thumb_h"]))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_scaled_chrome()
        if not hasattr(self._name_label, "setElideMode"):
            self._apply_name_label_text()
        self._layout_overlays()

    def _layout_overlays(self) -> None:
        scale = max(0.25, self.width() / float(CARD_BASE_WIDTH))
        overlay_scale = min(scale, 0.8)
        pad = max(1, int(round(2 * scale)))
        w = self._thumb.width()
        h = self._thumb.height()
        if w < 4 or h < 4:
            return
        btn_side = max(18, int(round(20 * overlay_scale)))
        review_pad = pad
        gap_combo_review = max(1, int(round(1 * scale)))
        budget = max(
            24,
            w - pad - review_pad - btn_side - gap_combo_review,
        )
        if self._version_combo:
            combo = self._version_combo
            cols = self._grid.get_grid_columns()
            font_pt = GRID_VERSION_FONT_MAX_PT
            if cols >= 5:
                font_pt = GRID_VERSION_FONT_MIN_PT
            elif cols == 4:
                font_pt = 9
            font = QtGui.QFont(combo.font())
            if font.pointSize() != font_pt:
                font.setPointSize(font_pt)
                combo.setFont(font)
                combo.view().setFont(font)
            combo.setMaximumWidth(budget)
            combo.updateGeometry()
            text = combo.currentText()
            fm = QtGui.QFontMetrics(combo.font())
            text_w = fm.horizontalAdvance(text) if text else 0
            text_pad = 16 if font_pt >= 9 else 14
            sh = combo.sizeHint()
            combo_w = min(max(text_w + text_pad, 38), budget)
            ch = max(19, min(sh.height(), max(19, int(round(21 * overlay_scale)))))
            y = h - ch - pad
            self._version_combo.setGeometry(pad, y, combo_w, ch)
            self._version_combo.raise_()
        self._review_btn.setGeometry(
            w - btn_side - review_pad,
            review_pad,
            btn_side,
            btn_side,
        )
        isz = max(10, btn_side - 7)
        self._review_btn.setIconSize(QtCore.QSize(isz, isz))
        self._review_btn.raise_()

    def set_section(self, section: Any) -> None:
        """Owning ``ProductsGridSection`` (deferred rebuild scope during drag)."""
        self._section = section

    @staticmethod
    def _mouse_global_point(event: QtGui.QMouseEvent) -> QtCore.QPoint:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def _apply_list_selection(
        self,
        lv: QtWidgets.QListView,
        index: QtCore.QModelIndex,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> None:
        sm = lv.selectionModel()
        if sm is None:
            return
        flags = QtCore.QItemSelectionModel.SelectionFlag
        rows = flags.Rows
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            sm.select(index, flags.Toggle | rows)
        elif modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            cur = sm.currentIndex()
            if cur.isValid() and cur.parent() == index.parent():
                sm.select(
                    QtCore.QItemSelection(cur, index),
                    flags.Select | rows,
                )
            else:
                sm.clearSelection()
                sm.select(index, flags.Select | rows)
        else:
            if not sm.isSelected(index):
                sm.clearSelection()
                sm.select(index, flags.Select | rows)
        sm.setCurrentIndex(index, flags.Current)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._grid.open_context_menu_from_card(
                self._mouse_global_point(event),
                self._flat_row,
            )
            event.accept()
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        idx = self._flat_index()
        if not idx.isValid():
            super().mousePressEvent(event)
            return
        lv = self._grid.list_view
        model = idx.model()
        drag_arm = bool(
            model is not None
            and (model.flags(idx) & QtCore.Qt.ItemIsDragEnabled)
        )
        self._apply_list_selection(lv, idx, event.modifiers())
        if drag_arm:
            self._drag_start_pos = QtCore.QPoint(event.pos())
            lv.viewport().setCursor(
                QtGui.QCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            )
            self._card_grid_interaction = True
            self._section.begin_user_interaction()
        else:
            self._drag_start_pos = None
        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._drag_start_pos is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
        ):
            lv = self._grid.list_view
            cb = getattr(lv, "_drag_data_callback", None)
            if callable(cb):
                dist = (event.pos() - self._drag_start_pos).manhattanLength()
                half_d = max(2, loader_drag_start_distance() // 2)
                if dist >= half_d:
                    _maybe_arm_drag_precache(lv)
                if dist >= loader_drag_start_distance():
                    setattr(lv, "_drag_precache_armed", False)
                    if self._card_grid_interaction:
                        self._card_grid_interaction = False
                        self._section.end_user_interaction()
                    self._drag_start_pos = None
                    lv.viewport().unsetCursor()
                    run_loader_drag_for_card(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        lv = self._grid.list_view
        if self._drag_start_pos is not None or self._card_grid_interaction:
            if self._card_grid_interaction:
                self._card_grid_interaction = False
                self._section.end_user_interaction()
            self._drag_start_pos = None
            setattr(lv, "_drag_precache_armed", False)
            lv.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _flat_index(self) -> QtCore.QModelIndex:
        return self._grid.card_model().index(self._flat_row, 0)

    def _apply_name_label_text(self) -> None:
        name = self._full_product_name
        lbl = self._name_label
        if hasattr(lbl, "setElideMode"):
            lbl.setText(name)
            return
        w = lbl.width()
        if w <= 0:
            lbl.setText(name)
            return
        fm = QtGui.QFontMetrics(lbl.font())
        lbl.setText(
            fm.elidedText(name, QtCore.Qt.TextElideMode.ElideRight, max(1, w))
        )

    def refresh_from_model(self) -> None:
        idx = self._flat_index()
        if not idx.isValid():
            return
        model = idx.model()
        name = model.data(idx, PRODUCT_NAME_ROLE) or model.data(idx, QtCore.Qt.DisplayRole) or ""
        self._full_product_name = name
        if self.width() > 0 and self.height() > 0:
            self._sync_scaled_chrome()
        self._apply_name_label_text()
        icon = model.data(idx, QtCore.Qt.DecorationRole)
        self.product_icon = icon if isinstance(icon, QtGui.QIcon) else None
        tw = self.width()
        iz = max(12, self._icon_label.width()) if tw > 0 else 20
        if self.product_icon and not self.product_icon.isNull():
            self._icon_label.setPixmap(self.product_icon.pixmap(iz, iz))
        else:
            self._icon_label.clear()

        self.version_id = model.data(idx, VERSION_ID_ROLE)
        product_id = model.data(idx, PRODUCT_ID_ROLE)
        self._product_id = product_id

        pm = self._grid.products_model()
        project = self._grid.controller.get_selected_project_name()
        vp_combo = self._grid.controller.get_version_padding(project)
        if product_id and pm:
            if self._version_combo is not None:
                if self._version_combo.get_product_id() != product_id:
                    self._version_combo.deleteLater()
                    self._version_combo = None
            if self._version_combo is None:
                self._version_combo = VersionComboBox(product_id, self._thumb)
                self._version_combo.setObjectName("ProductsGridVersionCombo")
                self._version_combo.view().setMinimumWidth(
                    GRID_VERSION_POPUP_MIN_WIDTH_PX
                )
                self._version_combo.installEventFilter(self)
                self._version_combo.value_changed.connect(
                    self._grid.on_card_version_changed
                )
                self._grid.apply_filters_to_combo(self._version_combo)
            version_items = pm.get_version_items_by_product_id(product_id) or []
            task_tags_by_vid = {}
            for vi in version_items:
                tid = vi.task_id
                tags = pm.get_task_tags_by_id(tid) if tid else set()
                task_tags_by_vid[vi.version_id] = set(tags) if tags else set()
            self._version_combo.blockSignals(True)
            self._version_combo.update_versions(
                version_items,
                self.version_id,
                task_tags_by_vid,
                version_padding=vp_combo,
            )
            self._version_combo.blockSignals(False)

        self._review_btn.setEnabled(bool(project and self.version_id))

        icon_color = get_default_entity_icon_color()
        self._review_btn.setIcon(_open_external_icon(icon_color))

        self._thumb.update()
        self.refresh_overlays()

    def refresh_overlays(self) -> None:
        self._layout_overlays()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        combo = self._version_combo
        context_targets = (self._review_btn,)
        if combo is not None:
            context_targets = context_targets + (combo,)

        if obj not in context_targets:
            return super().eventFilter(obj, event)

        if event.type() == QtCore.QEvent.Type.ContextMenu:
            ce = event
            if isinstance(ce, QtGui.QContextMenuEvent):
                self._grid.open_context_menu_from_card(
                    ce.globalPos(), self._flat_row
                )
                return True

        return super().eventFilter(obj, event)

    def _on_review_clicked(self) -> None:
        project = self._grid.controller.get_selected_project_name()
        vid = self.version_id
        if not project or not vid:
            return
        base = ayon_api.get_base_url().rstrip("/")
        query = urllib.parse.urlencode(
            {"project": project, "type": "version", "id": vid}
        )
        url = f"{base}/projects/{project}/products?{query}"
        webbrowser.open_new_tab(url)


class GridCellDelegate(QtWidgets.QStyledItemDelegate):
    """Thin selection/hover ring when a card indexWidget is present; else style panel."""

    def __init__(self, grid: Any, parent=None):
        super().__init__(parent)
        self._grid = grid

    def _item_view_for_paint(self, option) -> Optional[QtWidgets.QAbstractItemView]:
        """QAbstractItemView passes the viewport as option.widget, not the list."""
        w = option.widget
        if isinstance(w, QtWidgets.QAbstractItemView):
            return w
        if w is not None:
            p = w.parent()
            if isinstance(p, QtWidgets.QAbstractItemView):
                return p
        parent = self.parent()
        return parent if isinstance(parent, QtWidgets.QAbstractItemView) else None

    def sizeHint(self, option, index):  # noqa: ARG002
        return self._grid.get_grid_stride_size()

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        option.state &= ~QtWidgets.QStyle.State_HasFocus
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        item_view = self._item_view_for_paint(option)
        style_widget = option.widget or item_view
        style = style_widget.style() if style_widget else QtWidgets.QApplication.style()
        if item_view is not None and item_view.indexWidget(index) is not None:
            return

        style.drawPrimitive(
            QtWidgets.QStyle.PE_PanelItemViewItem,
            opt,
            painter,
            style_widget,
        )
