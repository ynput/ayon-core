"""Collapsible group section for Loader product grid (IconMode + cards per section)."""
from __future__ import annotations

from typing import Any, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.style import get_style_image_path

from .actions_utils import LoaderDragListView, LoaderDragTreeView
from .products_flatten_proxy import ProductsGridGroupFilterProxyModel
from .products_proxy_selection import (
    collect_version_ids_from_column0_indexes,
    find_root_group_column0_index,
)
from .products_single_group_row_proxy import SingleGroupRowProxyModel
from .products_tree_view_setup import (
    apply_delegate_filters_from_products_grid,
    configure_loader_products_tree_view,
)
from .products_grid_card_widget import GridCellDelegate, ProductsGridCardWidget
from .products_grid_constants import apply_grid_view_surface_palette, grid_view_surface_color
from .products_grid_geometry import (
    GRID_CONTENT_TOP_OFFSET_PX,
    GRID_DEFER_REBUILD_MS,
    GRID_READY_MIN_VIEWPORT_W,
    grid_list_height_for_rows,
)

_log = Logger.get_logger("loader.ProductsGridSection")

_BRANCH_OPEN_RES = ":/openpype/images/branch_open.png"
_BRANCH_CLOSED_RES = ":/openpype/images/branch_closed.png"


def _loader_branch_qicons() -> tuple[QtGui.QIcon, QtGui.QIcon]:
    """Same PNGs as list `#ProductView` ::branch (style.css)."""
    oc = get_style_image_path("branch_open")
    cc = get_style_image_path("branch_closed")
    if oc and cc:
        return QtGui.QIcon(oc), QtGui.QIcon(cc)
    return QtGui.QIcon(_BRANCH_OPEN_RES), QtGui.QIcon(_BRANCH_CLOSED_RES)


def _native_branch_icon_side_px() -> Optional[int]:
    """Intrinsic pixel size of branch assets (matches list tree painting)."""
    for src in (get_style_image_path("branch_closed"), _BRANCH_CLOSED_RES):
        if not src:
            continue
        pm = QtGui.QPixmap(src)
        if not pm.isNull():
            return int(max(pm.width(), pm.height()))
    return None


class GridGroupHeaderWidget(QtWidgets.QWidget):
    """Single `#ProductView` row + chevron; toggles section cards (matches list affordance)."""

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        section: "ProductsGridSection",
        group_key: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ProductsGridSectionHeader")
        self._section = section
        self._group_key = group_key
        self._expanded = False

        grid = section._owner
        pm = grid.products_proxy_model()

        self._row_proxy = SingleGroupRowProxyModel(self)
        self._row_proxy.setSourceModel(pm)
        ix0 = find_root_group_column0_index(pm, self._group_key)
        self._row_proxy.set_mapped_group_column0_index(ix0)

        row_h = max(32, self.fontMetrics().height() + 14)
        self._icon_open, self._icon_closed = _loader_branch_qicons()
        native_side = _native_branch_icon_side_px()
        self._branch_icon_side = native_side or max(18, self.fontMetrics().height() + 4)
        chevron_w = max(int(self._branch_icon_side) + 10, 28)

        self._toggle_btn = QtWidgets.QToolButton(self)
        self._toggle_btn.setObjectName("ProductsGridGroupChevron")
        self._toggle_btn.setAutoRaise(True)
        self._toggle_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._toggle_btn.setFixedSize(chevron_w, row_h)
        self._toggle_btn.clicked.connect(self._on_chevron_clicked)

        self._tree = LoaderDragTreeView(self)
        self._tree.setObjectName("ProductView")
        # Match ProductsWidget: model first so the header has a column count before
        # setSectionResizeMode / setColumnWidth (avoids Qt crashes on empty header).
        self._tree.setModel(self._row_proxy)
        self._delegates = configure_loader_products_tree_view(
            self._tree,
            section.products_model(),
            grid.controller,
            hide_folders_column=True,
        )
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setItemsExpandable(False)
        self._tree.setAnimated(False)
        self._tree.setSortingEnabled(False)
        self._tree.setAlternatingRowColors(False)
        self._tree.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._tree.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tree.setAllColumnsShowFocus(False)
        self._tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        # Full table column widths from configure_loader_products_tree_view exceed the
        # header strip width → horizontal scroll / clipped text. One visible column
        # matches group-row semantics (name in Product name) and fits the layout.
        self._apply_group_header_tree_layout()
        self._tree.setFixedHeight(row_h)

        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._tree.set_drag_data_callback(self._drag_data_callback)
        self._tree.set_drag_pixmap_context_callback(self._drag_pixmap_callback)
        self._tree.set_drag_precache(grid.drag_precache)

        pm.layoutChanged.connect(self.refresh_mapping)
        pm.modelReset.connect(self.refresh_mapping)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(0)
        row.addWidget(self._toggle_btn, 0)
        row.addWidget(self._tree, 1)

        self._apply_grid_surface_to_header()
        self.refresh_mapping()

    @property
    def _controller(self):
        return self._section.controller

    def _apply_group_header_tree_layout(self) -> None:
        """Keep the mini ProductView within the section width (no H-scroll / clipping)."""
        pmodel = self._section.products_model()
        if pmodel is None:
            return
        name_col = pmodel.product_name_col
        n = self._row_proxy.columnCount()
        for c in range(n):
            self._tree.setColumnHidden(c, c != name_col)
        self._tree.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._tree.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._tree.setTextElideMode(QtCore.Qt.ElideRight)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(name_col, QtWidgets.QHeaderView.Stretch)

    def apply_delegate_filters(self, grid: Any) -> None:
        apply_delegate_filters_from_products_grid(
            self._delegates,
            task_ids=grid._filter_task_ids,
            status_names=grid._filter_status_names,
            version_tags=grid._filter_version_tags,
            task_tags=grid._filter_task_tags,
        )

    def _apply_grid_surface_to_header(self) -> None:
        """Same `#1c2026` as scroll/grid body — avoids Loader chrome bleeding through."""
        fill = grid_view_surface_color()
        for w in (self, self._toggle_btn, self._tree, self._tree.viewport()):
            pal = w.palette()
            pal.setColor(QtGui.QPalette.ColorRole.Window, fill)
            pal.setColor(QtGui.QPalette.ColorRole.Base, fill)
            pal.setColor(QtGui.QPalette.ColorRole.Button, fill)
            w.setPalette(pal)
            w.setAutoFillBackground(True)

    def refresh_mapping(self) -> None:
        grid = self._section._owner
        pm = grid.products_proxy_model()
        self._row_proxy.setSourceModel(pm)
        ix = find_root_group_column0_index(pm, self._group_key)
        self._row_proxy.set_mapped_group_column0_index(ix)
        sm = self._tree.selectionModel()
        if sm is not None:
            # Do not select the row: selection paints like "focused product" on every group strip.
            sm.clearSelection()
        self._apply_group_header_tree_layout()
        self._apply_grid_surface_to_header()
        self._sync_chevron_icon()

    def _sync_chevron_icon(self) -> None:
        self._toggle_btn.setIcon(
            self._icon_open if self._expanded else self._icon_closed
        )
        side = int(self._branch_icon_side)
        self._toggle_btn.setIconSize(QtCore.QSize(side, side))

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._sync_chevron_icon()

    def is_expanded(self) -> bool:
        return self._expanded

    def _on_chevron_clicked(self) -> None:
        self._expanded = not self._expanded
        self._sync_chevron_icon()
        self.toggled.emit(self._expanded)

    def _drag_data_callback(self):
        grid = self._section._owner
        pm = grid.products_proxy_model()
        src = self._row_proxy.mapToSource(
            self._row_proxy.index(0, 0, QtCore.QModelIndex())
        )
        if not src.isValid():
            return None
        project_name = grid.products_model().get_last_project_name()
        if not project_name:
            return None
        vids = collect_version_ids_from_column0_indexes(pm, [src])
        if not vids:
            return None
        return (project_name, vids, "version")

    def _drag_pixmap_callback(self):
        grid = self._section._owner
        src = self._row_proxy.mapToSource(
            self._row_proxy.index(0, 0, QtCore.QModelIndex())
        )
        if not src.isValid():
            return None
        return grid.drag_pixmap_context_for_proxy_column0_indexes([src])

    def _on_tree_context_menu(self, point: QtCore.QPoint) -> None:
        vp = self._tree.viewport()
        self._section._owner.open_group_header_context_menu(
            self._group_key, vp.mapToGlobal(point)
        )


class ProductsGridSection(QtWidgets.QWidget):
    """One filtered IconMode list + optional collapsible header."""

    def __init__(
        self,
        owner: Any,
        group_key: Optional[str],
        show_header: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ProductsGridSection")
        self._owner = owner
        self._group_key = group_key
        self._show_header = show_header

        self._filter_proxy = ProductsGridGroupFilterProxyModel(group_key, self)
        self._filter_proxy.setSourceModel(owner.flatten_proxy)

        self._list_view = LoaderDragListView(self)
        self._list_view.setObjectName("ProductsGridView")
        self._list_view.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self._list_view.setMovement(QtWidgets.QListView.Movement.Static)
        self._list_view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self._list_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._list_view.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._list_view.setUniformItemSizes(True)
        self._list_view.setModel(self._filter_proxy)
        self._list_view.setItemDelegate(GridCellDelegate(owner, self._list_view))
        self._list_view.setSpacing(0)
        self._list_view.setSelectionRectVisible(True)
        self._list_view.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list_view.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._header = GridGroupHeaderWidget(self, group_key or "", self)
        self._header.setVisible(show_header)
        self._header.toggled.connect(self._on_header_toggled)

        self._list_holder = QtWidgets.QWidget(self)
        lh = QtWidgets.QVBoxLayout(self._list_holder)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(0)
        lh.addWidget(self._list_view)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header, 0)
        root.addWidget(self._list_holder, 0)

        self._rebuilding_index_widgets = False
        self._rebuild_index_widgets_deferred = False
        self._deferred_rebuild_attempts = 0
        self._syncing_index_widget_geometries = False
        self._index_widget_geometry_sync_queued = False

        self._list_view.customContextMenuRequested.connect(
            owner.open_context_menu_from_section_list
        )
        self._list_view.viewport().installEventFilter(self)
        self._list_view.verticalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )
        self._list_view.horizontalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )

        self._list_view.set_drag_data_callback(owner.get_section_drag_data_builder(self))
        self._list_view.set_drag_pixmap_context_callback(
            owner.get_section_drag_pixmap_builder(self)
        )
        self._list_view.set_drag_precache(owner.drag_precache)

        for w in (self, self._list_holder, self._list_view, self._list_view.viewport()):
            apply_grid_view_surface_palette(w)

    @property
    def group_key(self) -> Optional[str]:
        return self._group_key

    @property
    def list_view(self) -> LoaderDragListView:
        return self._list_view

    def card_model(self) -> ProductsGridGroupFilterProxyModel:
        return self._filter_proxy

    def products_model(self):
        return self._owner.products_model()

    @property
    def controller(self):
        return self._owner.controller

    def get_thumbnail_path(self, version_id: Optional[str]):
        return self._owner.get_thumbnail_path(version_id)

    def get_grid_columns(self) -> int:
        return self._owner.get_grid_columns()

    def get_grid_stride_size(self) -> QtCore.QSize:
        return self._owner.get_grid_stride_size()

    def apply_filters_to_combo(self, combo) -> None:
        self._owner.apply_filters_to_combo(combo)

    def apply_shared_geometry(
        self,
        inner_width: int,
        desired_columns: int,
        cached_tile: QtCore.QSize,
        grid_stride: QtCore.QSize,
        offset_x: int,
        offset_y: int,
    ) -> None:
        self._inner_width = max(1, int(inner_width))
        self._cached_tile = QtCore.QSize(cached_tile)
        self._grid_stride = QtCore.QSize(grid_stride)
        self._grid_content_offset_x = int(offset_x)
        self._grid_content_offset_y = int(offset_y)
        self._list_view.setSpacing(0)
        self._list_view.setIconSize(self._cached_tile)
        self._list_view.setGridSize(self._grid_stride)
        self._list_view.doItemsLayout()
        self._list_view.updateGeometries()
        self._update_list_minimum_height()
        self._schedule_index_widget_geometry_sync()

    def _update_list_minimum_height(self) -> None:
        row_count = self._filter_proxy.rowCount()
        cols = self._owner.get_grid_columns()
        stride = self._owner.get_grid_stride_size()
        h = grid_list_height_for_rows(
            row_count,
            cols,
            stride,
            top_offset=GRID_CONTENT_TOP_OFFSET_PX,
        )
        self._list_view.setMinimumHeight(h)
        self._list_view.setMaximumHeight(h)

    def set_section_expanded(self, expanded: bool) -> None:
        self._header.blockSignals(True)
        self._header.set_expanded(expanded)
        self._header.blockSignals(False)
        self._list_holder.setVisible(expanded)

    def _on_header_toggled(self, expanded: bool) -> None:
        self._list_holder.setVisible(expanded)
        self._owner.on_section_header_toggled(self, expanded)

    def _is_grid_viewport_ready_for_cards(self) -> bool:
        """IconMode needs drawable width; inner QListView width often stays 0 until polish.

        Prefer owner-passed `_inner_width` from `apply_shared_geometry` so grouped sections
        do not deadlock waiting on viewport metrics while thumbnails stay blank.
        Height is not required here — list height is set explicitly after geometry apply.
        """
        inner = int(getattr(self, "_inner_width", 0) or 0)
        vp = self._list_view.viewport()
        eff_w = max(vp.width(), inner, self._list_view.width())
        return eff_w >= GRID_READY_MIN_VIEWPORT_W

    def refresh_cards(self) -> None:
        if self._show_header:
            self._header.refresh_mapping()
        self._rebuild_index_widgets()

    def apply_header_delegate_filters(self, grid_widget: Any) -> None:
        if self._show_header:
            self._header.apply_delegate_filters(grid_widget)

    def _rebuild_index_widgets(self, *, force: bool = False) -> None:
        if self._rebuilding_index_widgets:
            return
        row_count = self._filter_proxy.rowCount()
        if (
            not force
            and row_count > 0
            and not self._is_grid_viewport_ready_for_cards()
        ):
            self._schedule_deferred_rebuild_index_widgets()
            return

        self._rebuild_index_widgets_deferred = False
        self._deferred_rebuild_attempts = 0

        tile = self._cached_tile if hasattr(self, "_cached_tile") else self._owner.get_tile_size()
        w, h = tile.width(), tile.height()
        self._rebuilding_index_widgets = True
        try:
            for row in range(row_count):
                try:
                    idx = self._filter_proxy.index(row, 0)
                    if not idx.isValid():
                        continue
                    existing = self._list_view.indexWidget(idx)
                    if isinstance(existing, ProductsGridCardWidget):
                        existing._flat_row = row
                        existing.setFixedSize(w, h)
                        existing.refresh_from_model()
                    else:
                        card = ProductsGridCardWidget(self, row, self._list_view.viewport())
                        card.setFixedSize(w, h)
                        self._list_view.setIndexWidget(idx, card)
                        card.refresh_from_model()
                        card.raise_()
                except BaseException:
                    _log.exception("row %s: exception during rebuild", row)
                    raise
        finally:
            self._rebuilding_index_widgets = False
            if row_count > 0:
                self._list_view.updateGeometries()
                self._sync_index_widget_geometries()
            self._owner.sync_section_selection_chrome(self)

    def _schedule_deferred_rebuild_index_widgets(self) -> None:
        if self._rebuild_index_widgets_deferred:
            return
        self._rebuild_index_widgets_deferred = True
        self._deferred_rebuild_attempts = 0
        QtCore.QTimer.singleShot(
            GRID_DEFER_REBUILD_MS,
            self._run_deferred_rebuild_index_widgets,
        )

    def _run_deferred_rebuild_index_widgets(self) -> None:
        if not self._rebuild_index_widgets_deferred:
            return
        force = False
        if self._filter_proxy.rowCount() > 0 and not self._is_grid_viewport_ready_for_cards():
            self._deferred_rebuild_attempts += 1
            _max_attempts = 60
            if self._deferred_rebuild_attempts < _max_attempts:
                QtCore.QTimer.singleShot(
                    GRID_DEFER_REBUILD_MS,
                    self._run_deferred_rebuild_index_widgets,
                )
                return
            _log.warning(
                "grid section %s: viewport still not ready after %s deferred tries; forcing card rebuild",
                self._group_key,
                _max_attempts,
            )
            force = True
        self._rebuild_index_widgets(force=force)

    def _schedule_index_widget_geometry_sync(self, *_args) -> None:
        if self._index_widget_geometry_sync_queued:
            return
        self._index_widget_geometry_sync_queued = True
        QtCore.QTimer.singleShot(0, self._sync_index_widget_geometries)

    def _sync_index_widget_geometries(self) -> None:
        self._index_widget_geometry_sync_queued = False
        if self._syncing_index_widget_geometries or self._rebuilding_index_widgets:
            return
        tile = self._cached_tile if hasattr(self, "_cached_tile") else self._owner.get_tile_size()
        if tile.width() < 1 or tile.height() < 1:
            return
        ox = getattr(self, "_grid_content_offset_x", self._owner.get_grid_content_offset_x())
        oy = getattr(self, "_grid_content_offset_y", GRID_CONTENT_TOP_OFFSET_PX)

        self._syncing_index_widget_geometries = True
        try:
            for row in range(self._filter_proxy.rowCount()):
                idx = self._filter_proxy.index(row, 0)
                if not idx.isValid():
                    continue
                w = self._list_view.indexWidget(idx)
                if not isinstance(w, ProductsGridCardWidget):
                    continue
                rect = self._list_view.visualRect(idx)
                if not rect.isValid():
                    continue
                top_left = rect.topLeft() + QtCore.QPoint(ox, oy)
                geom = QtCore.QRect(top_left, tile)
                if w.geometry() != geom:
                    w.setGeometry(geom)
                if not w.isVisible():
                    w.show()
                w.raise_()
        finally:
            self._syncing_index_widget_geometries = False

    def refresh_all_cards_from_model(self) -> None:
        for row in range(self._filter_proxy.rowCount()):
            w = self._list_view.indexWidget(self._filter_proxy.index(row, 0))
            if isinstance(w, ProductsGridCardWidget):
                w.refresh_from_model()
        self._sync_index_widget_geometries()

    def select_flat_row(
        self,
        flat_row: int,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> None:
        idx = self._filter_proxy.index(flat_row, 0)
        if not idx.isValid():
            return
        sm = self._list_view.selectionModel()
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Toggle)
        else:
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
        self._list_view.setCurrentIndex(idx)

    def open_context_menu_from_card(
        self,
        global_pos: QtCore.QPoint,
        flat_row: int,
    ) -> None:
        self._owner.open_context_menu_from_section_card(self, global_pos, flat_row)

    def on_card_version_changed(self, product_id: str, version_id: str) -> None:
        self._owner.on_card_version_changed(product_id, version_id)

    def eventFilter(self, obj, event):
        if obj is self._list_view.viewport() and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        ):
            self._schedule_index_widget_geometry_sync()
        if obj is self._list_view.viewport() and event.type() == QtCore.QEvent.Type.Wheel:
            return self._owner.section_viewport_wheel_event(event)
        return super().eventFilter(obj, event)
