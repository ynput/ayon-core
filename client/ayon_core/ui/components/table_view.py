"""AYTableView component module.

A flat, paginated table built on QTreeView with AYON styling.
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import (
    QAbstractProxyModel,
    QItemSelection,
    QModelIndex,
    QRect,
    Qt,
    Signal,  # type: ignore
)
from qtpy.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
)
from qtpy.QtWidgets import (
    QHeaderView,
    QStyle,
    QStyleOption,
    QStyleOptionViewItem,
    QToolButton,
    QTreeView,
    QWidget,
)

from ..style import enum_to_str, get_ayon_style
from ..style_types import StyleData
from ..variants import AYTableViewVariants
from .scroll_area import AYScrollBar
from .style_mixin import StyleMixin
from .table_model import PaginatedTableModel

from qtmaterialsymbols import get_icon  # type: ignore

log = logging.getLogger(__name__)


class AYTableHeader(StyleMixin, QHeaderView):
    """Custom QHeaderView that paints sections directly, bypassing QSS.

    Draws header sections using QPainter to avoid interference from
    QStyleSheetStyle when a QSS stylesheet is loaded at the app level.

    Args:
        orientation: Header orientation (Horizontal or Vertical).
        parent: Optional parent widget.
        style_model: Style data model; if None falls back to super().
        variant: Visual style variant name.
    """

    def __init__(
        self,
        orientation: Qt.Orientation,
        parent: QWidget | None = None,
        style_model: StyleData | None = None,
        variant: str = "default",
    ) -> None:
        super().__init__(orientation, parent)
        self._style_model = style_model
        self._variant_str = variant
        self._toggle_btn: QToolButton | None = None
        # self.setSortIndicatorShown(True)

    def paintSection(
        self,
        painter: QPainter,
        rect: QRect,
        logical_index: int,
    ) -> None:
        """Paint a single header section directly with QPainter.

        Falls back to the base implementation when no style model is
        available.

        Args:
            painter: The painter to draw with.
            rect: The bounding rectangle for this section.
            logical_index: The logical index of the section.
        """
        if self._style_model is None:
            super().paintSection(painter, rect, logical_index)
            return

        tbl_style = self._style_model.get_style(
            "AYTableView", self._variant_str
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(rect)

        # Draw cell background and border
        painter.setBrush(
            QBrush(QColor(tbl_style.get("header-background-color", "#272d35")))
        )
        painter.setPen(
            QPen(
                QColor(tbl_style.get("header-border-color", "#41474d")),
                tbl_style.get("header-border-width", 1),
            )
        )
        painter.drawRect(rect)

        # Label text
        padding = tbl_style.get("header-padding", [4, 8])
        h_pad = int(padding[1]) if len(padding) > 1 else 8
        v_pad = int(padding[0])
        text_rect = rect.adjusted(h_pad, v_pad, -h_pad, -v_pad)

        painter.setPen(QColor(tbl_style.get("header-color", "#c1c7ce")))
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        model = self.model()
        if model is not None:
            label = model.headerData(
                logical_index,
                self.orientation(),
                Qt.ItemDataRole.DisplayRole,
            )
            if label is not None:
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    str(label),
                )

        # Sort indicator
        if (
            self.isSortIndicatorShown()
            and self.sortIndicatorSection() == logical_index
        ):
            is_sortable = True
            if isinstance(
                model, PaginatedTableModel
            ) and 0 <= logical_index < len(model.columns):
                is_sortable = model.columns[logical_index].sortable
            if not is_sortable:
                painter.restore()
                return

            order = self.sortIndicatorOrder()
            icon_name = tbl_style.get("header-sort-indicator-icon")
            if icon_name:
                icon = get_icon(
                    icon_name,
                    color=tbl_style.get(
                        "header-sort-indicator-color", "#ffffff"
                    ),
                )
                size = tbl_style.get("header-sort-indicator-size", 16)
                margin = (rect.height() - size) / 2.0
                pixmap = icon.pixmap(size, size)
                target = rect.adjusted(
                    max(rect.width() - (size + h_pad), 0),
                    margin,
                    -h_pad,
                    -margin,
                )

                if order == Qt.SortOrder.AscendingOrder:
                    painter.save()
                    center = target.center()
                    painter.translate(center)
                    painter.rotate(180)
                    painter.translate(-center)
                    painter.drawPixmap(target, pixmap)
                    painter.restore()
                else:
                    painter.drawPixmap(target, pixmap)
            else:
                arrow = "▲" if order == Qt.SortOrder.AscendingOrder else "▼"
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignVCenter
                    | Qt.AlignmentFlag.AlignRight,
                    arrow,
                )

        painter.restore()

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Reposition the toggle button after a resize.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)
        self._reposition_toggle()

    def _reposition_toggle(self) -> None:
        """Move the toggle button to the right-centre of the header."""
        if self._toggle_btn is None:
            return
        btn = self._toggle_btn
        h = self.height()
        margin = max((h - btn.height()) // 2, 0)
        x = max(self.width() - btn.width() - margin, 0)
        btn.move(x, margin)

    # -------------------------------------------------------------------------


class AYTableView(StyleMixin, QTreeView):
    """AYON-styled flat table view.

    Subclasses QTreeView in flat-table mode (no tree indentation or
    expand toggles). Uses AYONStyle for all painting, a custom item
    delegate that draws directly bypassing any parent QSS, and
    AYScrollBar instances for scrollbars.

    The header is visible and styled via TableHeaderDrawer.

    When a PaginatedTableModel is set, columns that carry a
    ``widget_factory`` on their :class:`TableColumn` definition get a
    persistent editor in every row via ``openPersistentEditor``.  Qt
    calls ``setEditorData`` automatically whenever the model emits
    ``dataChanged`` for those cells, so server-push updates reach the
    widgets without any extra wiring.

    In tree mode, persistent editors are opened lazily — only for rows
    whose parent node is already expanded.  Rows under collapsed nodes
    receive their editors when the user (or code) expands that node,
    via the ``expanded`` signal handler.  This avoids creating widgets
    for the entire off-screen tree when Qt's layout pass eagerly
    triggers :meth:`fetchMore` for all visible nodes.

    Args:
        parent: Optional parent widget.
        variant: Visual style variant controlling colours.
    """

    Variants = AYTableViewVariants
    selection_changed = Signal(QItemSelection, QItemSelection)

    def __init__(
        self,
        parent: QWidget | None = None,
        variant: Variants = Variants.Default,
    ) -> None:
        self._variant_str: str = variant.value

        super().__init__(parent)

        style = get_ayon_style()
        self.setStyle(style)

        # Custom header — paints sections directly, bypassing QSS.
        header = AYTableHeader(
            Qt.Orientation.Horizontal,
            parent=self,
            style_model=style.model,
            variant=self._variant_str,
        )
        self.setHeader(header)

        # Self-contained: do not inherit parent background.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

        self.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, False
        )
        self._sync_viewport_palette()

        # Custom item delegate — paints cells directly.
        delegate = TableItemDelegate(
            parent=self,
            style_model=style.model,
            variant=self._variant_str,
        )
        delegate.setFont(self.font())
        self.setItemDelegate(delegate)

        # Styled scrollbars.
        vsb = AYScrollBar(Qt.Orientation.Vertical, self)
        self.setVerticalScrollBar(vsb)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hsb = AYScrollBar(Qt.Orientation.Horizontal, self)
        self.setHorizontalScrollBar(hsb)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Viewport-aware persistent-editor management (open-only strategy).
        # Tracks every QPersistentModelIndex for which openPersistentEditor
        # has already been called so the same editor is never opened twice.
        # Editors are never explicitly closed while scrolling: once built,
        # a dormant off-screen persistent editor costs near zero (Qt skips
        # its paintEvent), whereas re-creating it on scroll-back would cause
        # widget churn and redundant async thumbnail re-fetches.
        self._active_editor_pmis: set[QtCore.QPersistentModelIndex] = set()
        # Single-shot, zero-interval timer — fires once per event-loop
        # iteration so multiple rowsInserted bursts produce a single
        # _sync_viewport_editors call instead of one per batch.
        self._editor_sync_timer = QtCore.QTimer(self)
        self._editor_sync_timer.setSingleShot(True)
        self._editor_sync_timer.setInterval(0)
        self._editor_sync_timer.timeout.connect(self._sync_viewport_editors)
        vsb.valueChanged.connect(self._schedule_editor_sync)

        # Flat table — no tree features.
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)
        self.setIndentation(0)

        # Header visible.
        self.setHeaderHidden(False)

        # Selection behaviour.
        self.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)

        # No default frame — drawn manually in paintEvent.
        self.setFrameShape(QTreeView.Shape.NoFrame)

        # Alternating row colours disabled — delegate handles it.
        self.setAlternatingRowColors(False)

        # Hovered-row tracking: stores the visual rect of the currently
        # hovered row so we can force-repaint it when the mouse moves to a
        # different row.  Without this, the branch-indicator area (painted
        # by PE_IndicatorBranch, not the delegate) is never invalidated on
        # row transitions and stays highlighted until the next full repaint.
        self._hovered_row: int = -1
        self._hovered_row_rect: QRect = QRect()

        # Track the currently hovered index so we may pass hover state to
        # editors.
        self._hovered_index: QModelIndex = QModelIndex()

        # Column indices that have widget_factory set (cached from model).
        self._widget_col_indices: list[int] = []

        # Track model connections for cleanup.  Each entry is (source_object,
        # connection) so we can call the right object's .disconnect().
        self._model_connections: list[
            tuple[Any, QtCore.QMetaObject.Connection]
        ] = []

        # Node IDs that were expanded when the user last switched away from
        # tree mode.  Restored row-by-row as data is (re-)loaded in tree mode.
        self._expanded_node_ids: set[str] = set()

        # Open persistent editors for already-loaded children when a tree node
        # is expanded.  Complements _on_rows_inserted, which handles the case
        # where data is loaded after the node is already expanded (async mode).
        self.expanded.connect(self._schedule_editor_sync)

    def _sync_viewport_palette(self) -> None:
        """Apply the variant background colour to the viewport."""
        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        bg = QColor(tbl_style.get("background-color", "#252a31"))
        p = self.viewport().palette()
        p.setColor(QPalette.ColorRole.Base, bg)
        p.setColor(QPalette.ColorRole.Window, bg)
        self.viewport().setPalette(p)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the outer container background before items.

        Args:
            event: The paint event.
        """
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        bg = QColor(tbl_style.get("background-color", "#252a31"))
        painter.fillRect(self.viewport().rect(), bg)
        painter.end()

        super().paintEvent(event)

    def setModel(self, model: QtCore.QAbstractItemModel | None) -> None:
        """Set the data model and configure header and widgets.

        Args:
            model: The data model to display.
        """
        # Disconnect previous model signals.
        for obj, conn in self._model_connections:
            try:
                obj.disconnect(conn)
            except (RuntimeError, TypeError):
                pass
        self._model_connections.clear()

        # Clear viewport-editor tracking — the old model's editors are
        # invalidated by the model swap.
        self._active_editor_pmis.clear()
        self._editor_sync_timer.stop()

        super().setModel(model)

        if model is None:
            self._widget_col_indices = []
            return

        # Cache widget-factory column indices for hover state updates.
        source_mdl: Any = model
        if isinstance(model, QAbstractProxyModel):
            source_mdl = model.sourceModel()
        if isinstance(source_mdl, PaginatedTableModel):
            self._widget_col_indices = [
                i
                for i, col in enumerate(source_mdl.columns)
                if col.widget_factory is not None
            ]
        else:
            self._widget_col_indices = []

        # Configure header from column width hints.
        self._configure_header(model)

        # Schedule viewport-aware editor opening for existing rows.
        self._schedule_editor_sync()

        # Connect to rowsInserted for lazy-loaded rows.
        conn = model.rowsInserted.connect(self._on_rows_inserted)
        if conn is not None:
            self._model_connections.append((model, conn))

        # Clear editor tracking on model reset so stale PMIs don't linger.
        conn_reset = model.modelReset.connect(self._on_model_reset)
        if conn_reset is not None:
            self._model_connections.append((model, conn_reset))

        # Connect to the source PaginatedTableModel for tree mode changes.
        source: Any = model
        if isinstance(model, QAbstractProxyModel):
            source = model.sourceModel()
        if isinstance(source, PaginatedTableModel):
            conn2 = source.tree_mode_changed.connect(self._apply_tree_mode)
            if conn2 is not None:
                self._model_connections.append((source, conn2))
            self._apply_tree_mode(source._tree_mode)

    def _apply_tree_mode(self, tree_mode: bool) -> None:
        """Configure the view for flat-table or tree display.

        Args:
            tree_mode: ``True`` to enable tree indentation and expand
                controls; ``False`` for flat-table layout.
        """
        if not tree_mode:
            # Snapshot expansion state before the model resets.
            self._save_expansion_state()
        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        source = self._source_model()
        tree_pos = (
            source.tree_position
            if isinstance(source, PaginatedTableModel)
            else 0
        )
        if tree_mode:
            indent = int(tbl_style.get("indent", 16))
            self.setRootIsDecorated(True)
            self.setItemsExpandable(True)
            self.setIndentation(indent)
        else:
            self.setRootIsDecorated(False)
            self.setItemsExpandable(False)
            self.setIndentation(0)
        # Set the tree position to the column specified by the model.
        self.setTreePosition(tree_pos)

    def _source_model(self) -> QtCore.QAbstractItemModel | None:
        """Return the underlying source model, unwrapping any proxy layer.

        Returns:
            The source model, or ``None`` if no model is set.
        """
        model = self.model()
        if isinstance(model, QAbstractProxyModel):
            return model.sourceModel()
        return model

    def _repaint_row(self, row_rect: QRect) -> None:
        """Repaint the full viewport width for a given row rect.

        Args:
            row_rect: Visual rect of the row to repaint.
        """
        if row_rect.isNull():
            return
        vp = self.viewport()
        vp.update(QRect(0, row_rect.y(), vp.width(), row_rect.height()))

    def _configure_header(self, model: QtCore.QAbstractItemModel) -> None:
        """Set up header section sizes from model column hints.

        Args:
            model: The data model (may be a proxy wrapping a
                :class:`PaginatedTableModel`).
        """
        header = self.header()
        if header is None:
            return

        # Set header height from style.
        style = get_ayon_style()
        tbl_style = style.model.get_style("AYTableView", self._variant_str)
        header_height = int(tbl_style.get("header-height", 36))
        header.setFixedHeight(header_height)

        # Disable header highlight on selection.
        header.setHighlightSections(False)

        col_count = model.columnCount()
        if col_count == 0:
            return

        # Unwrap proxy to access PaginatedTableModel column definitions.
        source = (
            model.sourceModel()
            if isinstance(model, QAbstractProxyModel)
            else model
        )

        # Configure column widths
        if isinstance(source, PaginatedTableModel) and any(
            col_def.width > 0 for col_def in source.columns
        ):
            # Use column definitions from the model.
            for i, col_def in enumerate(source.columns):
                if i >= col_count:
                    break
                if col_def.width > 0:
                    header.resizeSection(i, col_def.width)
                    header.setSectionResizeMode(
                        i, QHeaderView.ResizeMode.Interactive
                    )
                else:
                    header.setSectionResizeMode(
                        i, QHeaderView.ResizeMode.Stretch
                    )
        else:
            # Default: stretch all columns equally.
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Enable sorting.
        # setSectionsClickable enables header click interaction (indicator
        # toggling + sortIndicatorChanged signal) without QTreeView's internal
        # sortIndicatorChanged → model.sort() connection that setSortingEnabled
        # would create behind our guard.
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if isinstance(source, PaginatedTableModel):
            header.sortIndicatorChanged.connect(
                lambda section, order: self._on_sort_indicator_changed(
                    section, order, source
                )
            )

    def _on_sort_indicator_changed(
        self, section: int, order: Qt.SortOrder, model: PaginatedTableModel
    ) -> None:
        cols = model.columns
        if 0 <= section < len(cols) and not cols[section].sortable:
            header = self.header()
            header.blockSignals(True)
            if 0 <= model._sort_column < len(cols):
                header.setSortIndicator(model._sort_column, model._sort_order)
            else:
                header.setSortIndicatorShown(False)
            header.blockSignals(False)
            return
        # Sortable column — delegate to the model.
        model.sort(section, order)
        # model.sort() triggers beginResetModel/endResetModel, which causes
        # QHeaderView.initializeSections() to wipe the sort indicator state.
        # Re-apply it explicitly after the reset.
        header = self.header()
        header.blockSignals(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(section, order)
        header.blockSignals(False)

    def _save_expansion_state(self) -> None:
        """Snapshot the node IDs of all expanded rows into ``_expanded_node_ids``.

        Called just before the model resets when switching from tree to flat
        mode, while the tree is still fully populated.
        """
        self._expanded_node_ids.clear()
        display_model = self.model()
        if display_model is None:
            return
        is_proxy = isinstance(display_model, QAbstractProxyModel)

        def _collect(parent_view_idx: QModelIndex) -> None:
            for row in range(display_model.rowCount(parent_view_idx)):
                child_view_idx = display_model.index(row, 0, parent_view_idx)
                if not self.isExpanded(child_view_idx):
                    continue
                src_idx = (
                    display_model.mapToSource(child_view_idx)  # type: ignore[union-attr]
                    if is_proxy
                    else child_view_idx
                )
                node = src_idx.internalPointer()
                if node is not None and node.node_id is not None:
                    self._expanded_node_ids.add(node.node_id)
                _collect(child_view_idx)

        _collect(QModelIndex())

    def _restore_expansion_in_range(
        self,
        parent: QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Expand any newly-inserted rows whose node ID was previously saved.

        Expanding a row triggers lazy child loading which fires more
        ``rowsInserted`` signals, so the full expansion tree is restored
        incrementally without extra bookkeeping.

        Args:
            parent: Parent index of the inserted rows.
            first: First inserted row index.
            last: Last inserted row index.
        """
        if not self._expanded_node_ids:
            return
        display_model = self.model()
        if display_model is None:
            return
        source = (
            display_model.sourceModel()
            if isinstance(display_model, QAbstractProxyModel)
            else display_model
        )
        if not isinstance(source, PaginatedTableModel):
            return
        if not source._tree_mode:
            return
        is_proxy = isinstance(display_model, QAbstractProxyModel)
        for row in range(first, last + 1):
            child_view_idx = display_model.index(row, 0, parent)
            src_idx = (
                display_model.mapToSource(child_view_idx)
                if is_proxy
                else child_view_idx
            )
            node = src_idx.internalPointer()
            if node is not None and node.node_id in self._expanded_node_ids:
                self.expand(child_view_idx)

    def _on_rows_inserted(
        self,
        parent: QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Open persistent editors and restore expansion for newly inserted rows.

        Args:
            parent: Parent index; supports non-root parents in tree mode.
            first: First inserted row index.
            last: Last inserted row index.
        """
        self._schedule_editor_sync()
        self._restore_expansion_in_range(parent, first, last)

    # ------------------------------------------------------------------
    # Viewport-aware persistent-editor helpers
    # ------------------------------------------------------------------

    def _schedule_editor_sync(self) -> None:
        """Schedule :meth:`_sync_viewport_editors` on the next event loop.

        Multiple calls within the same event-loop iteration collapse into
        a single sync because the timer is single-shot and we only start
        it when it is not already active.
        """
        if not self._editor_sync_timer.isActive():
            self._editor_sync_timer.start()

    def _on_model_reset(self) -> None:
        """Clear editor tracking after a model reset.

        Qt automatically closes all persistent editors on
        ``beginResetModel``, so ``_active_editor_pmis`` would hold stale
        entries.  Clearing it ensures :meth:`_sync_viewport_editors` starts
        from a clean slate, then schedules a sync so visible rows get their
        editors back.
        """
        self._hovered_index = QModelIndex()
        self._hovered_row = -1
        self._hovered_row_rect = QRect()
        self._active_editor_pmis.clear()
        self._schedule_editor_sync()

    def _get_visible_widget_indexes(self) -> list[QModelIndex]:
        """Return display-model indexes for visible cells with widget factories.

        Uses :meth:`QTreeView.indexBelow` to walk visible rows from the
        topmost visible item downwards, stopping as soon as the visual rect
        passes the viewport bottom.  Works correctly in both flat and tree
        mode.

        Returns:
            List of valid ``QModelIndex`` objects, one per (row, col) pair
            that is both visible and belongs to a widget-factory column.
        """
        model = self.model()
        if model is None:
            return []

        source = self._source_model()
        if not isinstance(source, PaginatedTableModel):
            return []

        widget_cols = [
            i
            for i, col in enumerate(source.columns)
            if col.widget_factory is not None
        ]
        if not widget_cols:
            return []

        vp_rect = self.viewport().rect()
        # indexAt() returns an invalid index when the viewport is empty.
        top_idx = self.indexAt(
            QtCore.QPoint(vp_rect.left(), vp_rect.top() + 1)
        )
        if not top_idx.isValid():
            return []
        # Normalise to column 0 so indexBelow() works predictably.
        top_idx = model.index(top_idx.row(), 0, top_idx.parent())

        results: list[QModelIndex] = []
        idx = top_idx
        while idx.isValid():
            visual = self.visualRect(idx)
            if visual.top() > vp_rect.bottom():
                break

            if not visual.isEmpty():
                for col in widget_cols:
                    col_idx = model.index(idx.row(), col, idx.parent())
                    if col_idx.isValid():
                        results.append(col_idx)

            idx = self.indexBelow(idx)

        return results

    def _sync_viewport_editors(self) -> None:
        """Open persistent editors for rows that just became visible.

        Called via :attr:`_editor_sync_timer` (single-shot, zero interval)
        so that bursts of ``rowsInserted`` signals collapse into a single
        call per event-loop iteration.  Also triggered on vertical scroll.

        Uses an **open-only** strategy: opens editors for visible rows that
        do not yet have one, but never closes editors for rows that have
        scrolled out of view.  A dormant off-screen persistent editor costs
        near zero (Qt skips its ``paintEvent``), while re-creating it on
        scroll-back would cause widget churn and redundant thumbnail
        re-fetches.

        :attr:`_active_editor_pmis` grows monotonically within a model
        lifetime and is reset by :meth:`_on_model_reset` so stale entries
        from a previous model do not block new editors after a reset.
        """
        for idx in self._get_visible_widget_indexes():
            pmi = QtCore.QPersistentModelIndex(idx)
            if pmi.isValid() and pmi not in self._active_editor_pmis:
                self.openPersistentEditor(pmi)
                self._active_editor_pmis.add(pmi)

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Schedule an editor sync when the view is resized.

        A viewport resize may reveal rows that have never been visible
        before.  Those rows need ``openPersistentEditor`` called on them
        before their thumbnail widgets can be created and painted.  The
        regular scroll-driven sync misses this case because the scrollbar
        value does not change on a pure resize.

        Args:
            event: The resize event.
        """
        super().resizeEvent(event)
        self._schedule_editor_sync()

    def mousePressEvent(  # type: ignore[override]
        self, event: "QtGui.QMouseEvent"
    ) -> None:
        """Deselect all items when clicking in an empty area.

        Args:
            event: Mouse press event.
        """
        index = self.indexAt(event.pos())
        if not index.isValid():
            self.clearSelection()
            self.setCurrentIndex(self.rootIndex())
            return
        super().mousePressEvent(event)

    def _set_row_state(self, row_idx: QModelIndex, hovered: bool) -> None:
        """Set ``row_state`` property on all editor widgets in a row.

        Iterates the cached widget-factory column indices and updates
        each persistent editor's dynamic property so the style system
        can react to hover, selected, and enabled states.

        Args:
            row_idx: Any valid index in the target row.
            hovered: Whether the row is being hovered.
        """
        state = QStyle.StateFlag.State_None
        if hovered:
            state |= QStyle.StateFlag.State_MouseOver
        if self.selectionModel().isSelected(row_idx):
            state |= QStyle.StateFlag.State_Selected
        if not self.model().flags(row_idx) & Qt.ItemFlag.ItemIsEnabled:
            state &= ~QStyle.StateFlag.State_Enabled

        for col in self._widget_col_indices:
            editor = self.indexWidget(row_idx.siblingAtColumn(col))
            if editor:
                editor.setProperty("row_state", state)
                editor.update()

    def mouseMoveEvent(self, event: "QtGui.QMouseEvent") -> None:  # type: ignore[override]
        """Track the hovered row and force-repaint it when it changes.

        Qt only invalidates the cell directly under the cursor on hover
        transitions.  The branch-indicator area (PE_IndicatorBranch) is
        outside that cell rect, so it never receives a repaint request when
        the cursor moves to a new row.  We force the viewport to repaint the
        full width of the previously-hovered row so the indicator clears.
        """
        new_idx = self.indexAt(event.pos())
        new_row = new_idx.row() if new_idx.isValid() else -1

        if new_row != self._hovered_row:
            # Clear hover state on the previous row's editors.
            if self._hovered_index.isValid():
                self._set_row_state(self._hovered_index, False)

            # Set hover state on the new row's editors.
            if new_idx.isValid():
                self._set_row_state(new_idx, True)

            self._hovered_index = new_idx

            # Repaint the old row so its indicator clears.
            self._repaint_row(self._hovered_row_rect)
            self._hovered_row = new_row
            self._hovered_row_rect = (
                self.visualRect(new_idx) if new_idx.isValid() else QRect()
            )

            # Repaint the new row so its indicator lights up immediately.
            self._repaint_row(self._hovered_row_rect)

        super().mouseMoveEvent(event)

    def leaveEvent(self, event: "QtCore.QEvent") -> None:
        """Clear hover tracking when the mouse exits the widget."""
        self._repaint_row(self._hovered_row_rect)
        self._hovered_row = -1
        self._hovered_row_rect = QRect()
        super().leaveEvent(event)

    def selectionChanged(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        """Override to emit a public signal on selection change.

        Args:
            selected: Newly selected items.
            deselected: Newly deselected items.
        """
        super().selectionChanged(selected, deselected)

        # Update row_state for newly selected rows
        for index in selected.indexes():
            self._set_row_state(index, True)

        # Update row_state for newly deselected rows
        for index in deselected.indexes():
            self._set_row_state(index, False)

        self.selection_changed.emit(selected, deselected)

    def drawBranches(self, painter, rect, index):
        """Draw branch indicators with AYONStyle directly.

        Bypasses ``self.style()`` because, when an application-level QSS is
        active, Qt wraps the widget's style in a ``QStyleSheetStyle`` proxy
        which would otherwise intercept ``PE_IndicatorBranch`` and apply
        QSS ``QTreeView::branch`` rules on top of (or instead of) ours.
        """
        style = get_ayon_style()  # the raw AYONStyle, never wrapped

        opt = QStyleOption()
        opt.rect = rect
        opt.palette = self.palette()
        state = QStyle.StateFlag.State_Item
        if self.model() is not None and self.model().hasChildren(index):
            state |= QStyle.StateFlag.State_Children
        if self.isExpanded(index):
            state |= QStyle.StateFlag.State_Open
        if self.selectionModel().isSelected(index):
            state |= QStyle.StateFlag.State_Selected
        if self.isEnabled():
            state |= QStyle.StateFlag.State_Enabled

        # Row-level hover: is the cursor on the same row as `index`?
        hovered_index = self.indexAt(
            self.viewport().mapFromGlobal(QCursor.pos())
        )
        if (
            hovered_index.isValid()
            and hovered_index.row() == index.row()
            and hovered_index.parent() == index.parent()
        ):
            state |= QStyle.StateFlag.State_MouseOver

        opt.state = state

        # Call our drawer directly, not through self.style().
        style.drawers[
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorBranch,
                "QTreeView",
            )
        ](opt, painter, self)


class TableItemDelegate(StyleMixin, QtWidgets.QStyledItemDelegate):
    """Item delegate for AYTableView that paints cells directly,
    bypassing QSS.

    Reads style data from the AYTableView style entry to draw cell
    backgrounds (hover, selected) and text/icons.

    Columns that carry a ``widget_factory`` on their :class:`TableColumn`
    definition get a persistent editor via :meth:`createEditor`.  Qt calls
    :meth:`setEditorData` both when the editor is first opened and
    automatically whenever the model emits ``dataChanged`` for that index,
    so server-push updates reach live widgets without extra wiring.
    User edits are written back via :meth:`setModelData`.

    Args:
        parent: The parent widget (expected to be an AYTableView instance).
        style_model: StyleData instance providing colour/dimension data.
        variant: The variant string used to look up the correct style.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        style_model: StyleData | None = None,
        variant: str = "default",
    ) -> None:
        super().__init__(parent)
        self._style_model = style_model
        self._variant_str = variant

    def _table_styles(self) -> dict[str, dict]:
        """Return base, hover and selected style dicts at once."""
        if self._style_model is None:
            raise ValueError("TableItemDelegate requires a style model")
        return self._style_model.get_styles(
            "AYTableView",
            self._variant_str,
            ["base", "hover", "selected"],
        )

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        """Return a fixed row height from the style data."""
        if self._style_model:
            style = self._style_model.get_style(
                "AYTableView", self._variant_str
            )
            h = int(style.get("item-height", 32))
        else:
            h = 32
        return QtCore.QSize(option.rect.width(), h)

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QWidget | None:
        """Return a widget for widget-factory columns; None otherwise.

        The returned widget is kept open permanently by the view via
        ``openPersistentEditor``.  Qt calls :meth:`setEditorData` once
        here and again automatically on every ``dataChanged`` emission
        for this index, so server-push updates reach the widget for free.

        Args:
            parent: Parent widget (viewport).
            option: Style option for the cell.
            index: Model index identifying the cell.

        Returns:
            A QWidget created by the column's ``widget_factory``, or
            ``None`` if the column has no factory.
        """
        from ..components.table_model import PaginatedTableModel

        src_model = index.model()
        if hasattr(src_model, "sourceModel"):
            src_model = src_model.sourceModel()
        if not isinstance(src_model, PaginatedTableModel):
            return None
        col = index.column()
        cols = src_model.columns
        if col < 0 or col >= len(cols):
            return None
        factory = cols[col].widget_factory
        if factory is None:
            return None
        return factory(index, parent)  # type: ignore[return-value]

    def setEditorData(
        self,
        editor: QWidget,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Push current model data into *editor* when the model changes.

        Called by Qt when the persistent editor is first opened and
        automatically whenever the model emits ``dataChanged`` for this
        index — server-push updates propagate to live widgets for free.

        This default implementation is a no-op suited to action widgets
        (e.g. buttons) that do not reflect model data.  Override or
        replace this method for data-reflecting widgets: read
        ``index.data(Qt.DisplayRole)`` (or a custom role) and push the
        value into *editor*.

        Args:
            editor: The persistent editor widget.
            index: Model index whose data changed.
        """

    def setModelData(
        self,
        editor: QWidget,
        model: QtCore.QAbstractItemModel,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Write committed user input from *editor* back to *model*.

        Called by Qt when the user commits an edit (e.g. presses Enter
        or the editor loses focus).

        This default implementation is a no-op suited to action widgets
        that do not write back to the model.  For interactive widget
        columns, read the current value from *editor* and call
        ``model.setData(index, value, Qt.EditRole)`` to propagate the
        change upstream (e.g. to the server).

        Args:
            editor: The persistent editor widget.
            model: The data model.
            index: Model index to write to.
        """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Paint a table cell directly, bypassing QStyle."""
        # Skip painting for cells covered by a persistent editor widget.
        from ..components.table_model import PaginatedTableModel

        src_model = index.model()
        if hasattr(src_model, "sourceModel"):
            src_model = src_model.sourceModel()
        if isinstance(src_model, PaginatedTableModel):
            col = index.column()
            cols = src_model.columns
            if 0 <= col < len(cols) and cols[col].widget_factory is not None:
                return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        state = opt.state
        is_selected = bool(state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        # State_MouseOver is only set for the cell directly under the cursor.
        # When hovering the branch-indicator column, other cells in the same
        # row don't receive it.  Fall back to a y-coordinate check so the
        # entire row highlights consistently.
        if not is_hovered and not is_selected:
            _view = self.parent()
            if type(_view).__name__ == "AYTableView" and hasattr(
                _view, "viewport"
            ):
                _cursor = _view.viewport().mapFromGlobal(QtGui.QCursor.pos())
                is_hovered = opt.rect.top() <= _cursor.y() < opt.rect.bottom()
        is_item = not bool(state & QStyle.StateFlag.State_Children)

        styles = self._table_styles()
        base_style = styles["base"]
        hover_style = styles["hover"]
        selected_style = styles["selected"]

        item_padding = base_style.get("item-padding", [4, 8])
        icon_text_spacing = int(base_style.get("icon-text-spacing", 6))

        # --- background ---
        if is_selected:
            bg_color = QColor(
                selected_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        elif is_hovered:
            bg_color = QColor(
                hover_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        else:
            bg_color = QColor(
                base_style.get(
                    "background-color-item" if is_item else "background-color",
                    "transparent",
                )
            )

        painter.setBrush(QBrush(bg_color))

        pen_width = base_style.get("border-width", 0)
        if pen_width > 0:
            pen_color = QColor(base_style.get("border-color", "#000000"))
            pen = QPen(pen_color)
            pen.setWidth(pen_width)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        column = index.column()
        if column == 1:
            painter.fillRect(opt.rect, bg_color)
            painter.drawPolyline(
                [
                    opt.rect.topLeft(),
                    opt.rect.topRight(),
                    opt.rect.bottomRight(),
                    opt.rect.bottomLeft(),
                ]
            )
        else:
            painter.drawRect(opt.rect)

        # --- text colour ---
        index_color = index.data(role=Qt.ItemDataRole.ForegroundRole)
        if is_selected:
            text_color = (
                index_color.color()
                if index_color
                else QColor(base_style.get("color", "#f4f5f5"))
            )
        else:
            text_color = (
                index_color.color()
                if index_color
                else QColor(base_style.get("color", "#f4f5f5"))
            )

        # disabled dimming
        if not (state & QStyle.StateFlag.State_Enabled):
            text_color.setAlpha(
                int(
                    text_color.alpha()
                    * base_style.get("disabled-opacity", 0.5)
                )
            )

        # --- icon + text layout ---
        content_rect = QRect(opt.rect).adjusted(
            item_padding[1],
            item_padding[0],
            -item_padding[1],
            -item_padding[0],
        )
        content_left = content_rect.left()

        if not opt.icon.isNull():
            icon_size = opt.decorationSize
            icon_rect = QRect(
                content_left,
                opt.rect.center().y() - icon_size.height() // 2,
                icon_size.width(),
                icon_size.height(),
            )
            mode = (
                QIcon.Mode.Normal
                if state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            opt.icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
            )
            content_left = icon_rect.right() + icon_text_spacing

        if opt.text:
            text_rect = QRect(opt.rect)
            text_rect.setLeft(content_left)
            text_rect.setRight(content_rect.right())
            painter.setPen(text_color)
            painter.setFont(self.font())
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                opt.text,
            )

        painter.restore()


# =============================================================================
# __main__ - visual test harness
# =============================================================================

if __name__ == "__main__":
    from typing import Callable

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

    def _make_button_factory(
        label: str,
    ) -> Callable[[QModelIndex, QWidget], QWidget]:
        """Create a widget factory that returns a small button.

        Args:
            label: Button text.

        Returns:
            A callable suitable for ``TableColumn.widget_factory``.
        """

        def _factory(index: QModelIndex, parent: QWidget) -> QWidget:
            from .buttons import AYButton

            btn = AYButton(
                label,
                variant=AYButton.Variants.Text,
                parent=parent,
            )
            btn.setFixedHeight(28)
            btn.clicked.connect(
                lambda: print(f"Button clicked: row={index.row()}")
            )
            return btn

        return _factory

    def _build() -> QtWidgets.QWidget:
        """Build test UI with one AYTableView per variant."""

        container = AYContainer(
            variant=AYContainer.Variants.High,
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=10,
        )

        # label + hierarchy switch
        top_bar = AYContainer(
            variant=AYContainer.Variants.High,
            layout=AYContainer.Layout.HBox,
        )
        label = QtWidgets.QLabel("variant: tree mode (hierarchical)")
        switch = AYCheckBox(
            "Show Hierarchy", variant=AYCheckBox.Variants.Button
        )
        top_bar.add_widget(label)
        top_bar.add_widget(switch)
        container.add_widget(top_bar)

        # define model — "actions" column uses a widget factory
        tree_columns = [
            TableColumn("thumb", "Thumbnail", width=75, sortable=False),
            TableColumn(
                "name", "Name", width=160, sortable=True, tree_position=True
            ),
            TableColumn("status", "Status", width=100, sortable=True),
            TableColumn("type", "Type", width=100, sortable=True),
            TableColumn("author", "Author", width=100, sortable=False),
            TableColumn("version", "Version", width=70, sortable=True),
            TableColumn(
                "actions",
                "Actions",
                width=90,
                sortable=False,
                widget_factory=_make_button_factory("Open"),
            ),
        ]
        tree_fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)
        tree_model = PaginatedTableModel(
            fetch_page=tree_fetch,
            columns=tree_columns,
            page_size=50,
        )
        tree_model.set_tree_mode(False)

        # define view
        tree_view = AYTableView(variant=AYTableView.Variants.Low)
        tree_view.setModel(tree_model)
        tree_view.setMinimumHeight(280)
        container.add_widget(tree_view)
        switch.toggled.connect(tree_model.set_tree_mode)

        tree_view.selection_changed.connect(
            lambda selected, deselected, tv=tree_view: print(
                "selection changed: "
                f"Selected {[i.data() for i in selected.indexes()]} "
                f"and deselected {[i.data() for i in deselected.indexes()]}) "
                f"(full selection: {[i.data() for i in tv.selectedIndexes()]})"
            )
        )

        container.setMinimumWidth(700)
        return container

    test(_build, style=Style.AyonStyleOverCSS)
