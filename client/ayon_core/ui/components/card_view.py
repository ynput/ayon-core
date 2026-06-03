"""AYCardView component module.

A flow-layout card view built on QAbstractItemView that displays
AYEntityCard widgets using the same PaginatedTableModel as AYTableView.
Supports collapsible grouping in tree mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,  # type: ignore
)
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontInfo,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QRegion,
)
from qtpy.QtWidgets import (
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from ..style import get_ayon_style
from ..variants import AYCardViewVariants
from .entity_card import CARD_RATIO, AYEntityCard
from .scroll_area import AYScrollBar
from .table_model import PaginatedTableModel

try:
    from qtmaterialsymbols import get_icon  # type: ignore
except ImportError:
    from ..vendor.qtmaterialsymbols import get_icon

log = logging.getLogger(__name__)


@dataclass
class _LayoutItem:
    """Maps a persistent model index to its card rect in content space."""

    index: QPersistentModelIndex
    rect: QRect


@dataclass
class _GroupLayout:
    """Layout info for one tree-mode group."""

    node_id: str
    label: str
    child_count: int
    header_rect: QRect
    collapsed: bool
    label_color: QBrush | None = None
    label_icon: QIcon | None = None
    items: list[_LayoutItem] = field(default_factory=list)
    parent_index: QPersistentModelIndex = field(
        default_factory=QPersistentModelIndex
    )


class _CardDelegate(QStyledItemDelegate):
    """Bridges PaginatedTableModel row data to AYEntityCard widgets.

    Args:
        card_width: Fixed pixel width of every card.
        card_data_mapper: Callable that converts a row_data dict to
            AYEntityCard keyword arguments.
        parent: Parent QObject.
    """

    def __init__(
        self,
        card_width: int,
        card_data_mapper: Callable[[dict[str, Any]], dict[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._card_width = card_width
        self._card_data_mapper = card_data_mapper

    def set_card_width(self, width: int) -> None:
        self._card_width = width

    def _card_height(self) -> int:
        return int(self._card_width / CARD_RATIO)

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        row_data = index.data(Qt.ItemDataRole.UserRole) or {}
        kwargs = self._card_data_mapper(row_data)
        card = AYEntityCard(width=self._card_width, parent=parent, **kwargs)
        return card

    def setEditorData(
        self, editor: QWidget, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if not isinstance(editor, AYEntityCard):
            return
        row_data = index.data(Qt.ItemDataRole.UserRole) or {}
        kwargs = self._card_data_mapper(row_data)
        for key, value in kwargs.items():
            try:
                setattr(editor, key, value)
            except AttributeError:
                pass

    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        editor.setGeometry(option.rect)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        return QSize(self._card_width, self._card_height())


class AYCardView(QAbstractItemView):
    """AYON-styled card view that displays AYEntityCard widgets in a flow
    layout.

    Uses the same PaginatedTableModel as AYTableView. In tree mode, groups
    are rendered as collapsible painted headers with cards flowing beneath
    each group.

    Args:
        parent: Optional parent widget.
        variant: Visual style variant.
        card_width: Initial card width in pixels.
        card_spacing: Horizontal and vertical spacing between cards.
        card_data_mapper: Callable mapping row_data dict to AYEntityCard
            keyword arguments. If None, no cards are created.
        group_header_height: Height of group header bars in tree mode.
    """

    Variants = AYCardViewVariants
    selection_changed = Signal(QItemSelection, QItemSelection)
    card_activated = Signal(QModelIndex)

    def __init__(
        self,
        parent: QWidget | None = None,
        variant: AYCardViewVariants = AYCardViewVariants.Default,
        card_width: int = 200,
        card_spacing: int = 8,
        card_data_mapper: Callable[[dict[str, Any]], dict[str, Any]]
        | None = None,
        group_header_height: int = 36,
    ) -> None:
        self._variant_str: str = variant.value
        super().__init__(parent)

        # FIXME: this is crashing
        # style = get_ayon_style()
        # self.setStyle(style)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, False
        )
        self._sync_viewport_palette()

        self._card_width: int = card_width
        self._card_spacing: int = card_spacing
        self._card_data_mapper: (
            Callable[[dict[str, Any]], dict[str, Any]] | None
        ) = card_data_mapper
        self._group_header_height: int = group_header_height
        self.scroll_step = max(1, int(self._card_width / CARD_RATIO * 0.1))

        vsb = AYScrollBar(Qt.Orientation.Vertical, self)
        self.setVerticalScrollBar(vsb)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        vsb.valueChanged.connect(self._on_scroll)

        self._delegate = _CardDelegate(
            card_width=self._card_width,
            card_data_mapper=card_data_mapper or (lambda r: {}),
            parent=self.viewport(),
        )
        self.setItemDelegate(self._delegate)

        self._active_editor_pmis: set[QPersistentModelIndex] = set()
        self._editor_sync_timer = QtCore.QTimer(self)
        self._editor_sync_timer.setSingleShot(True)
        self._editor_sync_timer.setInterval(0)
        self._editor_sync_timer.timeout.connect(self._sync_viewport_editors)

        self._model_connections: list[
            tuple[Any, QtCore.QMetaObject.Connection]
        ] = []

        self._collapsed_groups: set[str] = set()

        self._tree_layout: list[_GroupLayout] = []
        self._flat_layout: list[_LayoutItem] = []
        self._total_content_height: int = 0
        self._is_tree_mode: bool = False

        self._hovered_pmi: QPersistentModelIndex | None = None

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setFrameShape(QAbstractItemView.Shape.NoFrame)

    def set_card_width(self, width: int) -> None:
        self._card_width = width
        self.scroll_step = max(1, int(self._card_width / CARD_RATIO * 0.1))
        self._delegate.set_card_width(width)
        for pmi in self._active_editor_pmis:
            if not pmi.isValid():
                continue
            editor = self.indexWidget(QModelIndex(pmi))  # type: ignore
            if isinstance(editor, AYEntityCard):
                editor.resize_to_width(width)
        self._calculate_layout()
        self._sync_viewport_editors()

    def _sync_viewport_palette(self) -> None:
        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        tbl_style.set_context(self)
        bg = QColor(tbl_style.get("background-color", "#252a31"))
        p = self.viewport().palette()
        p.setColor(QPalette.ColorRole.Base, bg)
        p.setColor(QPalette.ColorRole.Window, bg)
        self.viewport().setPalette(p)

    def _source_model(self) -> QtCore.QAbstractItemModel | None:
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            return model.sourceModel()
        return model

    def setModel(self, model: QtCore.QAbstractItemModel | None) -> None:
        for obj, conn in self._model_connections:
            try:
                obj.disconnect(conn)
            except (RuntimeError, TypeError):
                pass
        self._model_connections.clear()

        self._active_editor_pmis.clear()
        self._editor_sync_timer.stop()

        super().setModel(model)

        if model is None:
            return

        conn = model.rowsInserted.connect(self._on_rows_inserted)
        if conn is not None:
            self._model_connections.append((model, conn))

        conn_reset = model.modelReset.connect(self._on_model_reset)
        if conn_reset is not None:
            self._model_connections.append((model, conn_reset))

        conn_dc = model.dataChanged.connect(self._on_data_changed)
        if conn_dc is not None:
            self._model_connections.append((model, conn_dc))

        conn_layout = model.layoutChanged.connect(self._on_layout_changed)
        if conn_layout is not None:
            self._model_connections.append((model, conn_layout))

        conn_removed = model.rowsRemoved.connect(self._on_rows_removed)
        if conn_removed is not None:
            self._model_connections.append((model, conn_removed))

        source: Any = model
        if isinstance(model, QSortFilterProxyModel):
            source = model.sourceModel()
        if isinstance(source, PaginatedTableModel):
            conn2 = source.tree_mode_changed.connect(
                self._on_tree_mode_changed
            )
            if conn2 is not None:
                self._model_connections.append((source, conn2))
            self._on_tree_mode_changed(source._tree_mode)

        self._schedule_layout_update()

    def _on_tree_mode_changed(self, tree_mode: bool) -> None:
        self._is_tree_mode = tree_mode
        self._schedule_layout_update()

    def _on_rows_inserted(
        self, parent: QModelIndex, first: int, last: int
    ) -> None:
        self._schedule_layout_update()

    def _on_model_reset(self) -> None:
        self._active_editor_pmis.clear()
        self._schedule_layout_update()

    def _on_data_changed(
        self,
        top_left: QModelIndex,
        bottom_right: QModelIndex,
        roles: list[int],
    ) -> None:
        self.viewport().update()

    def _on_layout_changed(self) -> None:
        """Handle layoutChanged emitted by the proxy on filter/sort changes.

        Closes all currently-open persistent editors whose
        ``QPersistentModelIndex`` is still valid (i.e. rows that survived
        the filter but may have been renumbered), then hides any orphaned
        ``AYEntityCard`` widgets whose PMIs became invalid (rows that were
        filtered out — ``closePersistentEditor`` is a no-op for invalid
        indices, so the widgets must be hidden manually).  Finally clears
        the tracking set and schedules a full layout rebuild so that only
        the rows that pass the new filter get fresh editors.
        """
        for pmi in self._active_editor_pmis:
            if pmi.isValid():
                self.closePersistentEditor(QModelIndex(pmi))  # type: ignore
        for child in self.viewport().children():
            if isinstance(child, AYEntityCard):
                child.hide()
        self._active_editor_pmis.clear()
        self._schedule_layout_update()

    def _on_rows_removed(
        self,
        parent: QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Schedule a layout update when rows are removed from the model.

        Args:
            parent: Parent index of the removed rows.
            first: First removed row index.
            last: Last removed row index (inclusive).
        """
        self._schedule_layout_update()

    def _on_scroll(self) -> None:
        self._reposition_visible_editors()
        self.viewport().update()
        self._schedule_editor_sync()

    def _schedule_layout_update(self) -> None:
        if not self._editor_sync_timer.isActive():
            self._editor_sync_timer.start()

    def _schedule_editor_sync(self) -> None:
        if not self._editor_sync_timer.isActive():
            self._editor_sync_timer.start()

    def _calculate_layout(self) -> None:
        model = self.model()
        self._tree_layout = []
        self._flat_layout = []
        self._total_content_height = 0

        if model is None or model.rowCount() == 0:
            self.updateGeometries()
            return

        vp_width = self.viewport().width()
        spacing = self._card_spacing
        card_w = self._card_width
        card_h = int(card_w / CARD_RATIO)
        margin = spacing

        if self._is_tree_mode:
            self._calculate_tree_layout(
                model, vp_width, margin, spacing, card_w, card_h
            )
        else:
            self._calculate_flat_layout(
                model, vp_width, margin, spacing, card_w, card_h
            )

        self.updateGeometries()

    def _flow_items(
        self,
        model: QtCore.QAbstractItemModel,
        parent_index: QModelIndex,
        start_y: int,
        vp_width: int,
        margin: int,
        spacing: int,
        card_w: int,
        card_h: int,
    ) -> tuple[list[_LayoutItem], int]:
        items: list[_LayoutItem] = []
        x = margin
        y = start_y
        line_height = 0
        row_count = model.rowCount(parent_index)

        for row in range(row_count):
            idx = model.index(row, 0, parent_index)
            if not idx.isValid():
                continue
            next_x = x + card_w + spacing
            if next_x - spacing > vp_width - margin and line_height > 0:
                x = margin
                y = y + line_height + spacing
                next_x = x + card_w + spacing
                line_height = 0
            rect = QRect(x, y, card_w, card_h)
            pmi = QPersistentModelIndex(idx)
            items.append(_LayoutItem(index=pmi, rect=rect))
            x = next_x
            line_height = max(line_height, card_h)

        end_y = y + line_height if line_height > 0 else start_y
        return items, end_y

    def _calculate_flat_layout(
        self,
        model: QtCore.QAbstractItemModel,
        vp_width: int,
        margin: int,
        spacing: int,
        card_w: int,
        card_h: int,
    ) -> None:
        items, end_y = self._flow_items(
            model,
            QModelIndex(),
            margin,
            vp_width,
            margin,
            spacing,
            card_w,
            card_h,
        )
        self._flat_layout = items
        self._total_content_height = end_y + margin

    def _calculate_tree_layout(
        self,
        model: QtCore.QAbstractItemModel,
        vp_width: int,
        margin: int,
        spacing: int,
        card_w: int,
        card_h: int,
    ) -> None:
        gh = self._group_header_height
        y = margin
        group_count = model.rowCount(QModelIndex())

        for g in range(group_count):
            group_idx = model.index(g, 0, QModelIndex())
            if not group_idx.isValid():
                continue

            node = None
            if isinstance(model, QSortFilterProxyModel):
                src_idx = model.mapToSource(group_idx)
                node = src_idx.internalPointer()
            else:
                node = group_idx.internalPointer()

            node_id = node.node_id if node is not None else str(g)
            label = group_idx.data(Qt.ItemDataRole.DisplayRole) or ""

            # DecorationRole / ForegroundRole data lives on the tree-position
            # column (e.g. "product/version"), NOT on column 0 ("thumb").
            # Resolve the right column from the source model when possible.
            src_model = self._source_model()
            tree_col = (
                src_model.tree_position
                if isinstance(src_model, PaginatedTableModel)
                else 0
            )
            meta_idx = (
                model.index(g, tree_col, QModelIndex())
                if tree_col != 0
                else group_idx
            )
            label_color = meta_idx.data(Qt.ItemDataRole.ForegroundRole)
            label_icon = meta_idx.data(Qt.ItemDataRole.DecorationRole)
            child_count = model.rowCount(group_idx)

            header_rect = QRect(0, y, vp_width, gh)
            y += gh + spacing

            collapsed = node_id in self._collapsed_groups

            if not collapsed:
                items, end_y = self._flow_items(
                    model,
                    group_idx,
                    y,
                    vp_width,
                    margin,
                    spacing,
                    card_w,
                    card_h,
                )
                y = end_y + spacing
            else:
                items = []

            self._tree_layout.append(
                _GroupLayout(
                    node_id=node_id,
                    label=label,
                    child_count=child_count,
                    header_rect=header_rect,
                    collapsed=collapsed,
                    label_color=label_color,
                    label_icon=label_icon,
                    items=items,
                    parent_index=QPersistentModelIndex(group_idx),
                )
            )

        self._total_content_height = y + margin

    def _all_layout_items(self) -> list[_LayoutItem]:
        if self._is_tree_mode:
            result = []
            for g in self._tree_layout:
                result.extend(g.items)
            return result
        return self._flat_layout

    def _rect_for_index(
        self, index: QModelIndex | QPersistentModelIndex
    ) -> QRect | None:
        pmi = QPersistentModelIndex(index)
        for item in self._all_layout_items():
            if item.index == pmi:
                return item.rect
        return None

    def _visible_rect(self, content_rect: QRect) -> QRect:
        offset = self.verticalOffset()
        return content_rect.translated(0, -offset)

    def horizontalOffset(self) -> int:
        return 0

    def verticalOffset(self) -> int:
        return self.verticalScrollBar().value()

    def visualRect(self, index: QModelIndex | QPersistentModelIndex) -> QRect:
        if not index.isValid():
            return QRect()
        content_rect = self._rect_for_index(index)
        if content_rect is None:
            return QRect()
        return self._visible_rect(content_rect)

    def scrollTo(
        self,
        index: QModelIndex | QPersistentModelIndex,
        hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.EnsureVisible,
    ) -> None:
        if not index.isValid():
            return
        content_rect = self._rect_for_index(index)
        if content_rect is None:
            return

        vsb = self.verticalScrollBar()
        vp_height = self.viewport().height()
        cur = vsb.value()

        if hint == QAbstractItemView.ScrollHint.EnsureVisible:
            if content_rect.top() < cur:
                vsb.setValue(content_rect.top())
            elif content_rect.bottom() > cur + vp_height:
                vsb.setValue(content_rect.bottom() - vp_height)
        elif hint == QAbstractItemView.ScrollHint.PositionAtTop:
            vsb.setValue(content_rect.top())
        elif hint == QAbstractItemView.ScrollHint.PositionAtBottom:
            vsb.setValue(content_rect.bottom() - vp_height)
        elif hint == QAbstractItemView.ScrollHint.PositionAtCenter:
            vsb.setValue(
                content_rect.top() - (vp_height - content_rect.height()) // 2
            )

    def indexAt(self, point: QPoint) -> QModelIndex:
        content_y = point.y() + self.verticalOffset()
        content_point = QPoint(point.x(), content_y)

        for item in self._all_layout_items():
            if item.rect.contains(content_point) and item.index.isValid():
                return QModelIndex(item.index)  # type: ignore

        return QModelIndex()

    def moveCursor(
        self,
        action: QAbstractItemView.CursorAction,
        modifiers: Qt.KeyboardModifier,
    ) -> QModelIndex:
        current = self.currentIndex()
        items = self._all_layout_items()
        if not items:
            return QModelIndex()

        if not current.isValid():
            first = items[0]
            return (
                QModelIndex(first.index)  # type: ignore
                if first.index.isValid()
                else QModelIndex()
            )

        cur_pmi = QPersistentModelIndex(current)
        cur_pos = -1
        for i, item in enumerate(items):
            if item.index == cur_pmi:
                cur_pos = i
                break

        if cur_pos == -1:
            return current

        if action in (
            QAbstractItemView.CursorAction.MoveRight,
            QAbstractItemView.CursorAction.MoveNext,
        ):
            new_pos = min(cur_pos + 1, len(items) - 1)
        elif action in (
            QAbstractItemView.CursorAction.MoveLeft,
            QAbstractItemView.CursorAction.MovePrevious,
        ):
            new_pos = max(cur_pos - 1, 0)
        elif action == QAbstractItemView.CursorAction.MoveDown:
            cur_rect = items[cur_pos].rect
            cur_center_x = cur_rect.center().x()
            best = cur_pos
            best_dist = float("inf")
            for i in range(cur_pos + 1, len(items)):
                r = items[i].rect
                if r.top() > cur_rect.bottom():
                    dist = abs(r.center().x() - cur_center_x)
                    if dist < best_dist:
                        best_dist = dist
                        best = i
                    elif dist > best_dist:
                        break
            new_pos = best
        elif action == QAbstractItemView.CursorAction.MoveUp:
            cur_rect = items[cur_pos].rect
            cur_center_x = cur_rect.center().x()
            best = cur_pos
            best_dist = float("inf")
            for i in range(cur_pos - 1, -1, -1):
                r = items[i].rect
                if r.bottom() < cur_rect.top():
                    dist = abs(r.center().x() - cur_center_x)
                    if dist < best_dist:
                        best_dist = dist
                        best = i
                    elif dist > best_dist:
                        break
            new_pos = best
        elif action == QAbstractItemView.CursorAction.MoveHome:
            new_pos = 0
        elif action == QAbstractItemView.CursorAction.MoveEnd:
            new_pos = len(items) - 1
        elif action == QAbstractItemView.CursorAction.MovePageUp:
            vp_h = self.viewport().height()
            cur_rect = items[cur_pos].rect
            target_y = cur_rect.top() - vp_h
            new_pos = 0
            for i, item in enumerate(items):
                if item.rect.top() >= target_y:
                    new_pos = i
                    break
        elif action == QAbstractItemView.CursorAction.MovePageDown:
            vp_h = self.viewport().height()
            cur_rect = items[cur_pos].rect
            target_y = cur_rect.top() + vp_h
            new_pos = len(items) - 1
            for i in range(cur_pos, len(items)):
                if items[i].rect.top() >= target_y:
                    new_pos = max(i - 1, cur_pos)
                    break
        else:
            return current

        target_item = items[new_pos]
        if target_item.index.isValid():
            return QModelIndex(target_item.index)  # type: ignore
        return current

    def isIndexHidden(
        self, index: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if not self._is_tree_mode:
            return False
        parent = index.parent()
        if not parent.isValid():
            return False
        node = None
        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            src = model.mapToSource(parent)
            node = src.internalPointer()
        else:
            node = parent.internalPointer()
        if node is None:
            return False
        node_id = node.node_id
        return node_id in self._collapsed_groups

    def setSelection(
        self, rect: QRect, flags: QItemSelectionModel.SelectionFlag
    ) -> None:
        offset = self.verticalOffset()
        content_rect = rect.translated(0, offset)
        sel = QItemSelection()
        model = self.model()
        if model is None:
            return
        for item in self._all_layout_items():
            if item.rect.intersects(content_rect) and item.index.isValid():
                idx = QModelIndex(item.index)  # type: ignore
                sel.select(idx, idx)
        self.selectionModel().select(sel, flags)

    def visualRegionForSelection(self, selection: QItemSelection) -> QRegion:
        region = QRegion()
        for idx in selection.indexes():
            r = self.visualRect(idx)
            if not r.isNull():
                region += QRegion(r)
        return region

    def updateGeometries(self) -> None:
        vsb = self.verticalScrollBar()
        vp_height = self.viewport().height()
        content_h = self._total_content_height
        if content_h > vp_height:
            vsb.setRange(0, content_h - vp_height)
            vsb.setPageStep(vp_height)
            vsb.setSingleStep(self.scroll_step)
        else:
            vsb.setRange(0, 0)
        super().updateGeometries()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._calculate_layout()
        self._reposition_visible_editors()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        tbl_style.set_context(self)
        bg = QColor(tbl_style.get("background-color", "#252a31"))
        painter.fillRect(self.viewport().rect(), bg)

        if self._is_tree_mode:
            self._paint_group_headers(painter, tbl_style)

        painter.end()

    def _paint_group_headers(
        self, painter: QPainter, tbl_style: dict[str, Any]
    ) -> None:
        offset = self.verticalOffset()
        vp_rect = self.viewport().rect()
        header_bg = QColor("transparent")
        header_fg = QColor(tbl_style.get("header-color", "#c1c7ce"))

        expand_icon_size = 16
        expand_icon_padding = 16
        icon_text_padding = 8

        # Set header font based on view font, but larger and bold.
        font = painter.font()
        header_font = QFont(font)
        header_font.setPixelSize(QFontInfo(font).pixelSize() + 3)
        header_font.setBold(True)
        painter.setFont(header_font)

        for group in self._tree_layout:
            visible_rect = group.header_rect.translated(0, -offset)
            if visible_rect.bottom() < 0:
                continue
            if visible_rect.top() > vp_rect.bottom():
                break

            painter.fillRect(visible_rect, header_bg)

            # Draw expand/collapse icon
            icon_name = (
                "expand_more" if not group.collapsed else "chevron_right"
            )
            try:
                expand_icon = get_icon(icon_name, color=header_fg.name())
                pixmap = expand_icon.pixmap(expand_icon_size, expand_icon_size)
                icon_x = expand_icon_padding
                icon_y = (
                    visible_rect.top()
                    + (visible_rect.height() - expand_icon_size) // 2
                )
                painter.drawPixmap(icon_x, icon_y, pixmap)
            except Exception:
                pass

            # Resolve label color — ForegroundRole returns QBrush, not QColor
            raw_color = group.label_color
            if isinstance(raw_color, QBrush):
                label_color: QColor | None = raw_color.color()
            elif isinstance(raw_color, QColor):
                label_color = raw_color
            else:
                label_color = None

            # Draw label icon if present
            text_x = expand_icon_padding + expand_icon_size + icon_text_padding
            label_icon_size = 16
            if isinstance(group.label_icon, QIcon):
                try:
                    licon_pixmap = group.label_icon.pixmap(
                        label_icon_size, label_icon_size
                    )
                    if not licon_pixmap.isNull():
                        licon_x = text_x
                        licon_y = (
                            visible_rect.top()
                            + (visible_rect.height() - label_icon_size) // 2
                        )
                        painter.drawPixmap(licon_x, licon_y, licon_pixmap)
                        text_x += label_icon_size + icon_text_padding
                except Exception as err:
                    log.debug(
                        "Failed to draw label icon: %s", err, exc_info=True
                    )

            # Draw group label
            text_rect = QRect(
                text_x,
                visible_rect.top(),
                visible_rect.width() - text_x - expand_icon_padding,
                visible_rect.height(),
            )
            painter.setPen(label_color or header_fg)

            label = group.label
            count_str = f"  ({group.child_count})"
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label + count_str,
            )
        painter.setFont(font)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        pos = event.pos()

        if self._is_tree_mode and event.button() == Qt.MouseButton.LeftButton:
            offset = self.verticalOffset()
            content_y = pos.y() + offset
            for group in self._tree_layout:
                if group.header_rect.contains(QPoint(pos.x(), content_y)):
                    self._toggle_group(group.node_id)
                    return

        idx = self.indexAt(pos)
        if idx.isValid():
            flags = QItemSelectionModel.SelectionFlag.ClearAndSelect
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                flags = QItemSelectionModel.SelectionFlag.Toggle
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                flags = QItemSelectionModel.SelectionFlag.Select
            self.selectionModel().select(QItemSelection(idx, idx), flags)
            self.setCurrentIndex(idx)

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        idx = self.indexAt(event.pos())
        if idx.isValid():
            self.card_activated.emit(idx)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        idx = self.indexAt(event.pos())
        new_pmi = QPersistentModelIndex(idx) if idx.isValid() else None

        if new_pmi != self._hovered_pmi:
            if self._hovered_pmi is not None and self._hovered_pmi.isValid():
                editor = self.indexWidget(QModelIndex(self._hovered_pmi))  # type: ignore
                if isinstance(editor, AYEntityCard):
                    editor.is_hover = False

            self._hovered_pmi = new_pmi

            if new_pmi is not None and new_pmi.isValid():
                editor = self.indexWidget(QModelIndex(new_pmi))  # type: ignore
                if isinstance(editor, AYEntityCard):
                    editor.is_hover = True

        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self._hovered_pmi is not None and self._hovered_pmi.isValid():
            editor = self.indexWidget(QModelIndex(self._hovered_pmi))  # type: ignore
            if isinstance(editor, AYEntityCard):
                editor.is_hover = False
        self._hovered_pmi = None
        super().leaveEvent(event)

    def selectionChanged(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        super().selectionChanged(selected, deselected)

        for idx in deselected.indexes():
            pmi = QPersistentModelIndex(idx)
            if pmi in self._active_editor_pmis:
                editor = self.indexWidget(QModelIndex(pmi))  # type: ignore
                if isinstance(editor, AYEntityCard):
                    editor.is_active = False

        for idx in selected.indexes():
            pmi = QPersistentModelIndex(idx)
            if pmi in self._active_editor_pmis:
                editor = self.indexWidget(QModelIndex(pmi))  # type: ignore
                if isinstance(editor, AYEntityCard):
                    editor.is_active = True

        self.selection_changed.emit(selected, deselected)

    def _toggle_group(self, node_id: str) -> None:
        if node_id in self._collapsed_groups:
            self._collapsed_groups.discard(node_id)
        else:
            self._collapsed_groups.add(node_id)

        self._active_editor_pmis.clear()
        self._calculate_layout()
        self._reposition_visible_editors()
        self.viewport().update()
        self._schedule_editor_sync()

    def _reposition_visible_editors(self) -> None:
        offset = self.verticalOffset()
        vp_rect = self.viewport().rect()

        for item in self._all_layout_items():
            if not item.index.isValid():
                continue
            visible_rect = item.rect.translated(0, -offset)
            if (
                visible_rect.bottom() < 0
                or visible_rect.top() > vp_rect.bottom()
            ):
                continue
            editor = self.indexWidget(QModelIndex(item.index))  # type: ignore
            if editor is not None:
                editor.setGeometry(visible_rect)

    def _get_visible_indexes(self) -> list[QModelIndex]:
        offset = self.verticalOffset()
        vp_rect = self.viewport().rect()
        results = []
        for item in self._all_layout_items():
            if not item.index.isValid():
                continue
            visible_rect = item.rect.translated(0, -offset)
            if visible_rect.bottom() < 0:
                continue
            if visible_rect.top() > vp_rect.bottom():
                continue
            results.append(QModelIndex(item.index))  # type: ignore
        return results

    def get_visible_indexes(self) -> list[QModelIndex]:
        """Return model indices for cards currently visible in the viewport.

        Returns:
            List of valid ``QModelIndex`` objects whose card rects
            intersect the viewport.
        """
        self._calculate_layout()
        return self._get_visible_indexes()

    def refresh_visible_editors(self) -> None:
        """Force ``setEditorData`` to be called for all visible card editors.

        Removes the visible cards from the active-editor set so that the
        next editor-sync pass re-opens their persistent editors and
        updates their data.  This is useful when external state (e.g. a
        thumbnail cache) has changed and the cards need to re-read it.
        """
        for idx in self._get_visible_indexes():
            self._active_editor_pmis.discard(QPersistentModelIndex(idx))
        self._schedule_editor_sync()

    def _maybe_fetch_more(self) -> None:
        """Trigger model pagination when the viewport nears content bottom.

        Must be called **after** ``_calculate_layout()`` has already run so
        that ``_total_content_height`` is up-to-date.  Uses the display model
        (``self.model()``) for all ``canFetchMore`` / ``fetchMore`` calls so
        that proxy mapping is preserved.
        """
        model = self.model()
        if model is None:
            return

        vp_height = self.viewport().height()
        offset = self.verticalOffset()
        total_h = self._total_content_height

        # Deduplicate parents so we never call fetchMore twice per pass.
        fetched: set[QPersistentModelIndex] = set()

        # --- flat-mode root fetch (also runs in tree mode for new top-level
        #     groups) ---
        root = QModelIndex()
        near_bottom = (
            total_h <= vp_height  # content shorter than viewport
            or offset + 2 * vp_height >= total_h
        )
        root_pmi = QPersistentModelIndex(root)
        if near_bottom and root_pmi not in fetched:
            if model.canFetchMore(root):
                model.fetchMore(root)
            fetched.add(root_pmi)

        # --- tree-mode: per-group child fetch ---
        if not self._is_tree_mode:
            return

        for group in self._tree_layout:
            if group.collapsed:
                continue
            if not group.parent_index.isValid():
                continue

            # Only fetch for groups whose content area is within the
            # look-ahead window (2 × viewport height ahead of current pos).
            group_top = group.header_rect.top()
            if group_top - offset >= 2 * vp_height:
                # Group is far below the fold — skip for now.
                break

            pmi = group.parent_index
            if pmi in fetched:
                continue
            group_idx = QModelIndex(pmi)  # type: ignore
            if model.canFetchMore(group_idx):
                model.fetchMore(group_idx)
            fetched.add(pmi)

    def _sync_viewport_editors(self) -> None:
        self._calculate_layout()
        offset = self.verticalOffset()
        vp_rect = self.viewport().rect()

        for item in self._all_layout_items():
            if not item.index.isValid():
                continue
            visible_rect = item.rect.translated(0, -offset)
            if visible_rect.bottom() < 0:
                continue
            if visible_rect.top() > vp_rect.bottom():
                continue

            pmi = item.index
            if pmi not in self._active_editor_pmis:
                self.openPersistentEditor(QModelIndex(pmi))  # type: ignore
                self._active_editor_pmis.add(pmi)

            editor = self.indexWidget(QModelIndex(pmi))  # type: ignore
            if editor is not None:
                editor.setGeometry(visible_rect)

        sel_model = self.selectionModel()
        if sel_model is not None:
            for pmi in self._active_editor_pmis:
                if not pmi.isValid():
                    continue
                idx = QModelIndex(pmi)  # type: ignore
                editor = self.indexWidget(idx)
                if isinstance(editor, AYEntityCard):
                    editor.is_active = sel_model.isSelected(idx)

        self._maybe_fetch_more()

    @property
    def card_width(self) -> int:
        return self._card_width

    @card_width.setter
    def card_width(self, value: int) -> None:
        self._card_width = value
        self._delegate._card_width = value
        self._active_editor_pmis.clear()
        self._schedule_layout_update()

    @property
    def card_spacing(self) -> int:
        return self._card_spacing

    @card_spacing.setter
    def card_spacing(self, value: int) -> None:
        self._card_spacing = value
        self._schedule_layout_update()

    @property
    def card_data_mapper(
        self,
    ) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
        return self._card_data_mapper

    @card_data_mapper.setter
    def card_data_mapper(
        self, value: Callable[[dict[str, Any]], dict[str, Any]] | None
    ) -> None:
        self._card_data_mapper = value
        self._delegate._card_data_mapper = value or (lambda r: {})
        self._active_editor_pmis.clear()
        self._schedule_layout_update()


# =============================================================================
# __main__ - visual test harness
# =============================================================================

if __name__ == "__main__":
    from qtpy import QtWidgets

    from ..tester import Style, test
    from .check_box import AYCheckBox
    from .container import AYContainer
    from .table_model import (
        HIERARCHICAL_TEST_DATA,
        PaginatedTableModel,
        TableColumn,
        make_hierarchical_test_fetch,
    )
    from .slider import AYSlider

    def _make_card_mapper(
        row_data: dict,
    ) -> dict:
        status_dict = None
        if row_data.get("status"):
            status_dict = {
                "name": row_data["status"],
                "icon": row_data.get("status__icon", ""),
                "color": row_data.get("status__color", ""),
            }
        return {
            "header": row_data.get("name", ""),
            "title": row_data.get("type", ""),
            "title_icon": row_data.get("name__icon", ""),
            "image_icon": row_data.get("thumb__icon", "image"),
            "status": status_dict,
            "version": row_data.get("version", ""),
        }

    def _build() -> QtWidgets.QWidget:
        container = AYContainer(
            variant=AYContainer.Variants.High,
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=10,
        )

        top_bar = AYContainer(
            variant=AYContainer.Variants.High,
            layout=AYContainer.Layout.HBox,
            layout_spacing=10,
        )
        label = QtWidgets.QLabel("AYCardView — card width slider + tree mode")
        switch = AYCheckBox(
            "Show Hierarchy", variant=AYCheckBox.Variants.Button
        )

        width_slider = AYSlider(
            label="Card Width",
            variant=AYSlider.Variants.Default,
            value=200,
            minimum=120,
            maximum=300,
            step=10,
        )
        width_slider.setFixedWidth(160)

        top_bar.add_widget(label)
        top_bar.add_widget(width_slider)
        top_bar.add_widget(switch)
        container.add_widget(top_bar)

        columns = [
            TableColumn("name", "Name", width=160, sortable=True),
            TableColumn("status", "Status", width=100, sortable=True),
            TableColumn("type", "Type", width=100, sortable=True),
            TableColumn("version", "Version", width=70, sortable=True),
        ]

        _tree_mode: list[bool] = [False]
        _all_leaf_rows: list[dict] = [
            row
            for rows in HIERARCHICAL_TEST_DATA.values()
            for row in rows
            if not row.get("has_children", False)
        ]
        _hier_fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)

        def _fetch(
            page: int,
            page_size: int,
            sort_key: str | None = None,
            descending: bool = False,
            parent_id: str | None = None,
        ) -> list[dict]:
            if parent_id is not None:
                return _hier_fetch(
                    page, page_size, sort_key, descending, parent_id
                )
            if _tree_mode[0]:
                return _hier_fetch(page, page_size, sort_key, descending, None)
            rows = list(_all_leaf_rows)
            if sort_key:
                rows = sorted(
                    rows,
                    key=lambda r: (
                        r.get(sort_key) is None,
                        str(r.get(sort_key, "")),
                    ),
                    reverse=descending,
                )
            start = page * page_size
            return rows[start : start + page_size]

        model = PaginatedTableModel(
            fetch_page=_fetch,
            columns=columns,
            page_size=50,
        )
        model.set_tree_mode(False)

        card_view = AYCardView(
            variant=AYCardView.Variants.Low,
            card_width=200,
            card_spacing=8,
            card_data_mapper=_make_card_mapper,
        )
        card_view.setModel(model)
        card_view.setMinimumHeight(400)
        container.add_widget(card_view)

        def _on_tree_mode_toggle(enabled: bool) -> None:
            _tree_mode[0] = enabled
            model.set_tree_mode(enabled)

        switch.toggled.connect(_on_tree_mode_toggle)
        width_slider.value_changed.connect(
            lambda v: card_view.set_card_width(v)
        )

        container.setMinimumWidth(800)
        return container

    test(_build, style=Style.AyonStyleOverCSS)
