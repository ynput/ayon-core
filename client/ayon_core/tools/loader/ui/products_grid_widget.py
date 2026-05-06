"""Grid view of products: web-style cards with thumbnail, version combo, review link."""
from __future__ import annotations

import collections
import numbers
from typing import Any, Dict, List, Optional

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib import Logger
from ayon_core.tools.utils.lib import format_version

from .products_flatten_proxy import ProductsFlattenProxyModel
from .products_grid_card_widget import (
    CARD_BASE_HEIGHT,
    CARD_BASE_WIDTH,
    GridCellDelegate,
    ProductsGridCardWidget,
    layout_dims_for_cell_width,
    tile_size_for_cell_width,
)
from .products_model import (
    FOLDER_ID_ROLE,
    PRODUCT_ID_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_ID_ROLE,
    VERSION_NAME_ROLE,
    VERSION_THUMBNAIL_ID_ROLE,
)
from .products_delegates import VersionComboBox
from .actions_utils import DragPayloadPrecache, LoaderDragListView, show_actions_menu

# Legacy float scale range (migration from LOADER_VIEW_SCALE_KEY only).
MIN_SCALE = 0.5
MAX_SCALE = 2.0
DEFAULT_SCALE = 1.0

# Discrete columns slider / persisted user preference.
GRID_COLUMNS_MIN = 3
GRID_COLUMNS_MAX = 12


def _min_cell_width_for_thumb_inner(min_inner: int = 90) -> int:
    """Smallest cell width where thumb inner plate still reaches min_inner (readable)."""
    for tw in range(48, 600):
        if layout_dims_for_cell_width(tw)["inner_w"] >= min_inner:
            return tw
    return max(48, int(CARD_BASE_WIDTH * 0.65))


MIN_CELL_WIDTH = _min_cell_width_for_thumb_inner()

# IconMode horizontal/vertical gap between cells (not included in setGridSize; Qt adds it).
GRID_CELL_SPACING = 6
# QListView.IconMode wraps items early when the final grid cell lands exactly on
# the viewport edge; reserve visible slack in every row to keep the requested
# last column on the row without taking over QListView's scrollbar internals.
GRID_ROW_WRAP_SAFETY_PX = 6

# Product rows can arrive before the loader window has completed its first
# layout pass. Building index widgets into that tiny transient viewport can
# crash Qt, so defer non-empty rebuilds until the view has a real size.
GRID_READY_MIN_VIEWPORT_W = 200
GRID_READY_MIN_VIEWPORT_H = 100
GRID_DEFER_REBUILD_MS = 50
GRID_VIEW_MARGIN_MIN_PX = 8
GRID_CONTENT_TOP_OFFSET_PX = 10
GRID_CONTENT_RIGHT_NUDGE_PX = 4


def columns_from_density_scale(scale: float) -> int:
    """Map legacy 0.5–2.0 view scale to a column count (fewer columns when scale is high)."""
    s = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
    span = GRID_COLUMNS_MAX - GRID_COLUMNS_MIN
    u = (s - MIN_SCALE) / (MAX_SCALE - MIN_SCALE)
    return int(round(GRID_COLUMNS_MAX - u * span))


DEFAULT_GRID_COLUMNS = 5

_log = Logger.get_logger("loader.ProductsGridWidget")


class ProductsGridWidget(QtWidgets.QWidget):
    """Grid of product cards; shares selection with list and drives same controller signals."""

    refreshed = QtCore.Signal()
    selection_changed = QtCore.Signal()
    merged_products_selection_changed = QtCore.Signal()
    scale_change_requested = QtCore.Signal(int)
    column_bounds_changed = QtCore.Signal(int, int)
    grid_columns_clamped = QtCore.Signal(int)

    def __init__(
        self,
        controller: Any,
        flatten_proxy: ProductsFlattenProxyModel,
        parent=None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._flatten_proxy = flatten_proxy
        self._thumbnail_path_by_version_id: Dict[str, Optional[str]] = {}
        self._grid_columns = DEFAULT_GRID_COLUMNS
        self._cached_tile = QtCore.QSize(CARD_BASE_WIDTH, CARD_BASE_HEIGHT)
        self._grid_stride = QtCore.QSize(
            CARD_BASE_WIDTH + GRID_CELL_SPACING,
            CARD_BASE_HEIGHT + GRID_CELL_SPACING,
        )
        self._last_col_bounds = (GRID_COLUMNS_MIN, GRID_COLUMNS_MAX)
        self._emitted_col_bounds: Optional[tuple[int, int]] = None
        self._selected_versions_info: List[dict] = []
        self._selected_merged_products: List[dict] = []

        self._filter_task_ids: set = set()
        self._filter_status_names = None
        self._filter_version_tags = None
        self._filter_task_tags = None
        self._version_changed_connected = False
        self._rebuilding_index_widgets = False
        self._rebuild_index_widgets_deferred = False
        self._syncing_index_widget_geometries = False
        self._index_widget_geometry_sync_queued = False
        self._grid_content_offset_x = 0
        self._grid_content_offset_y = 0

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
        self._list_view.setModel(flatten_proxy)
        self._list_view.setItemDelegate(GridCellDelegate(self, self._list_view))
        self._list_view.setSpacing(0)
        self._list_view.setSelectionRectVisible(True)

        self._grid_bottom_spacer = QtWidgets.QWidget(self)
        self._grid_bottom_spacer.setFixedHeight(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._list_view, 1)
        layout.addWidget(self._grid_bottom_spacer, 0)

        self._apply_grid_geometry()
        self._rebuild_index_widgets()

        self._flatten_proxy.modelReset.connect(self._on_flatten_model_reset)
        self._flatten_proxy.layoutChanged.connect(self._on_flatten_layout_changed)
        self._flatten_proxy.rowsInserted.connect(self._on_rows_changed)
        self._flatten_proxy.rowsRemoved.connect(self._on_rows_changed)
        self._flatten_proxy.dataChanged.connect(self._on_flat_data_changed)
        self._list_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        self._list_view.customContextMenuRequested.connect(self._on_context_menu)
        self._list_view.viewport().installEventFilter(self)
        self._list_view.verticalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )
        self._list_view.horizontalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )

        self._apply_grid_chrome_background()
        self._list_view.set_drag_data_callback(self._get_grid_drag_data)
        self._list_view.set_drag_pixmap_context_callback(
            self._grid_drag_pixmap_context
        )
        self._drag_precache = DragPayloadPrecache()
        self._list_view.set_drag_precache(self._drag_precache)

    @property
    def list_view(self) -> LoaderDragListView:
        """QListView hosting grid cards (rubber-band / drag targets)."""
        return self._list_view

    def _grid_drag_pixmap_context(self):
        """Labels + cached thumbnail path for composite drag pixmap."""
        data = self._get_grid_drag_data()
        if not data:
            return None
        project_name, version_ids, _ = data
        first_vid = next(iter(version_ids))
        thumb_path = self._thumbnail_path_by_version_id.get(first_vid)
        indexes = self._list_view.selectionModel().selectedIndexes()
        ix = indexes[0] if indexes else None
        model = self._list_view.model()
        product_label = ""
        version_label = ""
        if ix is not None and ix.isValid() and model is not None:
            product_label = str(model.data(ix, PRODUCT_NAME_ROLE) or "")
            raw_ver = model.data(ix, VERSION_NAME_ROLE)
            if isinstance(raw_ver, numbers.Integral):
                version_label = format_version(
                    raw_ver,
                    version_padding=self._controller.get_version_padding(
                        project_name
                    ),
                )
            else:
                version_label = str(raw_ver or "")
        return {
            "thumbnail_path": thumb_path,
            "product_label": product_label,
            "version_label": version_label,
            "count": len(version_ids),
        }

    def _get_grid_drag_data(self):
        """Return (project_name, version_ids, entity_type) for loader DnD (grid view)."""
        project_name = self._controller.get_selected_project_name()
        if not project_name:
            return None
        selection_model = self._list_view.selectionModel()
        model = self._list_view.model()
        if selection_model is None or model is None:
            return None
        version_ids = set()
        indexes_queue = collections.deque(selection_model.selectedIndexes())
        while indexes_queue:
            index = indexes_queue.popleft()
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                indexes_queue.append(child_index)
            version_id = model.data(index, VERSION_ID_ROLE)
            if version_id is not None:
                version_ids.add(version_id)
        if not version_ids:
            return None
        return (project_name, version_ids, "version")

    def _apply_grid_chrome_background(self) -> None:
        """#1c2026 behind list + viewport (stylesheet may not paint QAbstractScrollArea viewport)."""
        fill = QtGui.QColor("#1c2026")
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, fill)
        self.setPalette(pal)
        vp = self._list_view.viewport()
        vp.setAutoFillBackground(True)
        vpal = vp.palette()
        vpal.setColor(QtGui.QPalette.Window, fill)
        vpal.setColor(QtGui.QPalette.Base, fill)
        vp.setPalette(vpal)

    def get_tile_size(self) -> QtCore.QSize:
        """Card pixel size (index widget fixed size, tile math)."""
        return self._tile_size()

    def get_grid_stride_size(self) -> QtCore.QSize:
        """QListView IconMode cell stride when gridSize is set (spacing() is ignored by Qt)."""
        return self._grid_stride

    def compute_column_bounds(self) -> tuple[int, int]:
        """Feasible column count range for the current viewport width."""
        inner = self._viewport_inner_width_for_columns()
        return self._compute_column_bounds_for_inner(inner)

    def _viewport_inner_width_for_columns(self) -> int:
        """Usable drawable width for column math, with optional scrollbar reserve."""
        lv = self._list_view
        inner_raw = max(1, lv.viewport().width())
        vsb = lv.verticalScrollBar()
        if (
            vsb is not None
            and not vsb.isVisible()
            and lv.verticalScrollBarPolicy()
            != QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ):
            sb_ext = lv.style().pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent, None, lv
            )
            return max(1, inner_raw - sb_ext)
        return inner_raw

    def _compute_column_bounds_for_inner(self, inner: int) -> tuple[int, int]:
        sp = GRID_CELL_SPACING
        lo = GRID_COLUMNS_MIN
        hi = lo
        for n_test in range(GRID_COLUMNS_MAX, GRID_COLUMNS_MIN - 1, -1):
            stride_test = max(1, (inner // n_test) - GRID_ROW_WRAP_SAFETY_PX)
            tw_test = stride_test - sp
            if tw_test >= MIN_CELL_WIDTH:
                hi = n_test
                break
        return lo, max(lo, hi)

    def get_column_bounds(self) -> tuple[int, int]:
        return (int(self._last_col_bounds[0]), int(self._last_col_bounds[1]))

    def _apply_grid_geometry(self) -> None:
        """Grid tile size from thumb-only aspect; row fits the drawable viewport."""
        lv = self._list_view
        base_sp = GRID_CELL_SPACING
        top_m = 0
        inner = self._viewport_inner_width_for_columns()
        lo, hi = self._compute_column_bounds_for_inner(inner)
        self._last_col_bounds = (lo, hi)
        if self._emitted_col_bounds != (lo, hi):
            self._emitted_col_bounds = (lo, hi)
            self.column_bounds_changed.emit(lo, hi)

        start_cols = int(self._grid_columns)
        n = max(lo, min(hi, start_cols))
        sp = base_sp
        # Qt IconMode wraps when the final cell lands exactly on the viewport edge.
        # Leave a pixel of row slack so the requested column count is stable.
        stride_w = max(1, (inner // n) - GRID_ROW_WRAP_SAFETY_PX)
        tw = stride_w - sp
        while n > lo and tw < MIN_CELL_WIDTH:
            n -= 1
            stride_w = max(1, (inner // n) - GRID_ROW_WRAP_SAFETY_PX)
            tw = stride_w - sp
        self._grid_columns = n
        if int(self._grid_columns) != start_cols:
            self.grid_columns_clamped.emit(int(self._grid_columns))

        tw_final = tw
        sp_layout = sp

        # IconMode + setGridSize: Qt ignores spacing(); bake gaps into stride (see get_grid_stride_size).
        lv.setSpacing(0)
        self._cached_tile = tile_size_for_cell_width(tw_final)
        tile_h = self._cached_tile.height()
        self._grid_stride = QtCore.QSize(stride_w, tile_h + sp_layout)
        row_w = self._grid_columns * self._grid_stride.width()
        self._grid_content_offset_x = max(
            GRID_VIEW_MARGIN_MIN_PX,
            (inner - row_w) // 2,
        ) + GRID_CONTENT_RIGHT_NUDGE_PX
        self._grid_content_offset_y = GRID_CONTENT_TOP_OFFSET_PX
        lv.setViewportMargins(0, top_m, 0, 0)
        lv.setIconSize(self._cached_tile)
        lv.setGridSize(self._grid_stride)
        lv.doItemsLayout()
        lv.updateGeometries()
        self._schedule_index_widget_geometry_sync()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        prev = QtCore.QSize(self._cached_tile)
        self._apply_grid_geometry()
        if (
            self._rebuild_index_widgets_deferred
            and self._is_grid_viewport_ready_for_cards()
        ):
            self._rebuild_index_widgets_deferred = False
            self._rebuild_index_widgets()
            if self._flatten_proxy.rowCount() > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)
            return
        if prev != self._cached_tile:
            self._rebuild_index_widgets()
            if self._flatten_proxy.rowCount() > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)
        else:
            self._sync_index_widget_geometries()
            self._list_view.viewport().update()

    @property
    def controller(self) -> Any:
        return self._controller

    @property
    def flatten_proxy(self) -> ProductsFlattenProxyModel:
        return self._flatten_proxy

    def products_model(self):
        sm = self._flatten_proxy.sourceModel()
        if sm is None:
            return None
        return sm.sourceModel()

    def get_scale_factor(self) -> float:
        """Visual scale vs base card width (overlays); driven by pixel tile width."""
        return self._cached_tile.width() / float(CARD_BASE_WIDTH)

    def get_grid_columns(self) -> int:
        return int(self._grid_columns)

    def _tile_size(self) -> QtCore.QSize:
        return self._cached_tile

    def set_overlay_bottom_height(self, h: int) -> None:
        """Reserve h pixels below the list (not inside the scroll viewport).

        QListView IconMode + setViewportMargins(bottom>0) can desync hit-testing
        from index widgets; keep the viewport rectangular and use a spacer strip.
        """
        self._grid_bottom_spacer.setFixedHeight(max(0, int(h)))
        self._apply_grid_geometry()

    def set_grid_columns(self, n: int) -> None:
        prev_tile = QtCore.QSize(self._cached_tile)
        lo, hi = self._last_col_bounds
        self._grid_columns = max(lo, min(hi, int(n)))
        self._apply_grid_geometry()
        if prev_tile != self._cached_tile:
            self._rebuild_index_widgets()
        else:
            self._sync_index_widget_geometries()
            self._list_view.viewport().update()

    def set_scale_factor(self, value: float) -> None:
        """Legacy adapter: maps old 0.5–2.0 density scale to column count once."""
        self.set_grid_columns(columns_from_density_scale(value))

    def get_thumbnail_path(self, version_id: Optional[str]) -> Optional[str]:
        if not version_id:
            return None
        return self._thumbnail_path_by_version_id.get(version_id)

    def _ensure_products_model_signals(self) -> None:
        pm = self.products_model()
        if pm is None or self._version_changed_connected:
            return
        pm.version_changed.connect(self._on_products_model_version_changed)
        self._version_changed_connected = True

    def _on_products_model_version_changed(self) -> None:
        self._update_thumbnail_cache()
        self._refresh_all_cards()

    def _on_flat_data_changed(
        self,
        top_left: QtCore.QModelIndex,
        bottom_right: QtCore.QModelIndex,
        roles=None,
    ) -> None:
        _ = roles
        for row in range(top_left.row(), bottom_right.row() + 1):
            w = self._list_view.indexWidget(self._flatten_proxy.index(row, 0))
            if isinstance(w, ProductsGridCardWidget):
                w.refresh_from_model()

    def _update_thumbnail_cache(self) -> None:
        project_name = self._controller.get_selected_project_name()
        if not project_name:
            self._thumbnail_path_by_version_id.clear()
            return
        version_ids = set()
        for row in range(self._flatten_proxy.rowCount()):
            idx = self._flatten_proxy.index(row, 0)
            vid = idx.data(VERSION_ID_ROLE)
            if vid:
                version_ids.add(vid)
        if not version_ids:
            self._thumbnail_path_by_version_id.clear()
            return
        path_by_id = self._controller.get_thumbnail_paths(
            project_name, "version", version_ids
        )
        self._thumbnail_path_by_version_id = dict(path_by_id)

    def _refresh_grid_from_proxy(self) -> None:
        self._ensure_products_model_signals()
        self._update_thumbnail_cache()
        self._rebuild_index_widgets()

    def _scroll_grid_to_top_deferred(self) -> None:
        idx = self._flatten_proxy.index(0, 0)
        if idx.isValid():
            self._list_view.scrollTo(
                idx,
                QtWidgets.QAbstractItemView.ScrollHint.PositionAtTop,
            )
        vsb = self._list_view.verticalScrollBar()
        if vsb is not None:
            vsb.setValue(0)
        self._sync_index_widget_geometries()

    def _on_flatten_model_reset(self) -> None:
        self._refresh_grid_from_proxy()
        if self._flatten_proxy.rowCount() > 0:
            QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)

    def _on_flatten_layout_changed(self) -> None:
        self._refresh_grid_from_proxy()

    def _on_rows_changed(self, *_args) -> None:
        self._ensure_products_model_signals()
        self._update_thumbnail_cache()
        self._rebuild_index_widgets()

    def _is_grid_viewport_ready_for_cards(self) -> bool:
        viewport = self._list_view.viewport()
        return (
            viewport.width() >= GRID_READY_MIN_VIEWPORT_W
            and viewport.height() >= GRID_READY_MIN_VIEWPORT_H
        )

    def _schedule_deferred_rebuild_index_widgets(self) -> None:
        if self._rebuild_index_widgets_deferred:
            return
        self._rebuild_index_widgets_deferred = True
        QtCore.QTimer.singleShot(
            GRID_DEFER_REBUILD_MS,
            self._run_deferred_rebuild_index_widgets,
        )

    def _run_deferred_rebuild_index_widgets(self) -> None:
        if not self._rebuild_index_widgets_deferred:
            return
        if (
            self._flatten_proxy.rowCount() > 0
            and not self._is_grid_viewport_ready_for_cards()
        ):
            return
        self._rebuild_index_widgets_deferred = False
        self._rebuild_index_widgets()

    def _rebuild_index_widgets(self) -> None:
        if self._rebuilding_index_widgets:
            return
        row_count = self._flatten_proxy.rowCount()
        if row_count > 0 and not self._is_grid_viewport_ready_for_cards():
            self._apply_grid_geometry()
            self._schedule_deferred_rebuild_index_widgets()
            return
        self._apply_grid_geometry()
        tile = self._tile_size()
        w, h = tile.width(), tile.height()
        self._rebuilding_index_widgets = True
        try:
            for row in range(row_count):
                try:
                    idx = self._flatten_proxy.index(row, 0)
                    if not idx.isValid():
                        continue
                    existing = self._list_view.indexWidget(idx)
                    if isinstance(existing, ProductsGridCardWidget):
                        # Update in-place — never replace a live index widget.
                        # Replacing via setIndexWidget causes Qt to delete the old
                        # widget while PySide2/PyQt5 Python Signal state is still
                        # live, producing a C++ use-after-free crash.
                        existing._flat_row = row
                        existing.setFixedSize(w, h)
                        existing.refresh_from_model()
                    else:
                        card = ProductsGridCardWidget(
                            self, row, self._list_view.viewport()
                        )
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
            self._sync_card_selection_chrome()
            if row_count > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)

    def _refresh_all_cards(self) -> None:
        for row in range(self._flatten_proxy.rowCount()):
            w = self._list_view.indexWidget(self._flatten_proxy.index(row, 0))
            if isinstance(w, ProductsGridCardWidget):
                w.refresh_from_model()
        self._sync_index_widget_geometries()

    def _schedule_index_widget_geometry_sync(self, *_args) -> None:
        if self._index_widget_geometry_sync_queued:
            return
        self._index_widget_geometry_sync_queued = True
        QtCore.QTimer.singleShot(0, self._sync_index_widget_geometries)

    def _sync_index_widget_geometries(self) -> None:
        """Keep persistent card widgets aligned with QListView visual rects.

        Qt's IconMode geometry can lag behind setGridSize/viewport-margin updates.
        The delegate still owns item sizing; this only pins each indexWidget to the
        top-left of the current cell rect after the view has recalculated layout.
        """
        self._index_widget_geometry_sync_queued = False
        if self._syncing_index_widget_geometries:
            return
        if self._rebuilding_index_widgets:
            return

        tile = self._tile_size()
        if tile.width() < 1 or tile.height() < 1:
            return

        self._syncing_index_widget_geometries = True
        try:
            for row in range(self._flatten_proxy.rowCount()):
                idx = self._flatten_proxy.index(row, 0)
                if not idx.isValid():
                    continue
                w = self._list_view.indexWidget(idx)
                if not isinstance(w, ProductsGridCardWidget):
                    continue
                rect = self._list_view.visualRect(idx)
                if not rect.isValid():
                    continue
                top_left = rect.topLeft() + QtCore.QPoint(
                    self._grid_content_offset_x,
                    self._grid_content_offset_y,
                )
                geom = QtCore.QRect(top_left, tile)
                if w.geometry() != geom:
                    w.setGeometry(geom)
                if not w.isVisible():
                    w.show()
                w.raise_()
        finally:
            self._syncing_index_widget_geometries = False

    def _on_card_version_value_changed(self, product_id: str, version_id: str) -> None:
        pm = self.products_model()
        if pm:
            pm.set_product_version(product_id, version_id)

    def _apply_filters_to_combo(self, combo: VersionComboBox) -> None:
        combo.set_tasks_filter(self._filter_task_ids)
        combo.set_statuses_filter(self._filter_status_names)
        combo.set_version_tags_filter(self._filter_version_tags)
        combo.set_task_tags_filter(self._filter_task_tags)

    def set_tasks_filter(self, task_ids):
        self._filter_task_ids = set(task_ids) if task_ids else set()
        self._apply_all_card_combos()

    def set_statuses_filter(self, status_names):
        if status_names is not None:
            status_names = set(status_names)
        self._filter_status_names = status_names
        self._apply_all_card_combos()

    def set_version_tags_filter(self, version_tags):
        if version_tags is not None:
            version_tags = set(version_tags)
        self._filter_version_tags = version_tags
        self._apply_all_card_combos()

    def set_task_tags_filter(self, task_tags):
        if task_tags is not None:
            task_tags = set(task_tags)
        self._filter_task_tags = task_tags
        self._apply_all_card_combos()

    def _apply_all_card_combos(self) -> None:
        for row in range(self._flatten_proxy.rowCount()):
            w = self._list_view.indexWidget(self._flatten_proxy.index(row, 0))
            if isinstance(w, ProductsGridCardWidget) and w.version_combo:
                self._apply_filters_to_combo(w.version_combo)

    def select_flat_row(
        self,
        flat_row: int,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> None:
        idx = self._flatten_proxy.index(flat_row, 0)
        if not idx.isValid():
            return
        sm = self._list_view.selectionModel()
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            sm.select(
                idx,
                QtCore.QItemSelectionModel.SelectionFlag.Toggle,
            )
        else:
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
        self._list_view.setCurrentIndex(idx)

    def open_context_menu_from_card(
        self,
        global_pos: QtCore.QPoint,
        flat_row: int,
    ) -> None:
        """Card chrome RMB (combo/header/review): select row then open loader menu.

        Same pipeline as `ProductsWidget._on_context_menu`: `get_action_items`,
        `show_actions_menu`, then `trigger_action_item`.
        """
        idx = self._flatten_proxy.index(flat_row, 0)
        if not idx.isValid():
            return
        sm = self._list_view.selectionModel()
        if not sm.isSelected(idx):
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
            self._list_view.setCurrentIndex(idx)
        self._run_context_menu_at_global(global_pos)

    def _on_context_menu(self, point: QtCore.QPoint) -> None:
        sm = self._list_view.selectionModel()
        if sm is not None and not self._list_view.selectedIndexes():
            idx = self._list_view.indexAt(point)
            if idx.isValid():
                sm.clearSelection()
                sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
                self._list_view.setCurrentIndex(idx)
        vp = self._list_view.viewport()
        self._run_context_menu_at_global(vp.mapToGlobal(point))

    def _run_context_menu_at_global(self, global_point: QtCore.QPoint) -> None:
        selection_model = self._list_view.selectionModel()
        model = self._list_view.model()
        project_name = self._controller.get_selected_project_name()

        version_ids = set()
        indexes_queue = collections.deque()
        indexes_queue.extend(selection_model.selectedIndexes())
        while indexes_queue:
            index = indexes_queue.popleft()
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                indexes_queue.append(child_index)
            version_id = model.data(index, VERSION_ID_ROLE)
            if version_id is not None:
                version_ids.add(version_id)

        action_items = self._controller.get_action_items(
            project_name, version_ids, "version"
        )
        result = show_actions_menu(
            action_items,
            global_point,
            len(version_ids) == 1,
            self,
        )
        action_item, options = result
        if action_item is None or options is None:
            return

        self._controller.trigger_action_item(
            identifier=action_item.identifier,
            project_name=project_name,
            selected_ids=version_ids,
            selected_entity_type="version",
            data=action_item.data,
            options=options,
            form_values={},
        )

    def _sync_card_selection_chrome(self) -> None:
        sm = self._list_view.selectionModel()
        if sm is None:
            return
        for row in range(self._flatten_proxy.rowCount()):
            idx = self._flatten_proxy.index(row, 0)
            w = self._list_view.indexWidget(idx)
            if isinstance(w, ProductsGridCardWidget):
                w.set_grid_row_selected(idx.isValid() and sm.isSelected(idx))

    def _on_selection_changed(self) -> None:
        selected_version_ids = set()
        selected_versions_info = []
        for idx in self._list_view.selectionModel().selectedIndexes():
            if idx.column() != 0:
                continue
            if not idx.isValid():
                continue
            version_id = idx.data(VERSION_ID_ROLE)
            product_id = idx.data(PRODUCT_ID_ROLE)
            folder_id = idx.data(FOLDER_ID_ROLE)
            thumbnail_id = idx.data(VERSION_THUMBNAIL_ID_ROLE)
            if version_id:
                selected_version_ids.add(version_id)
                selected_versions_info.append(
                    {
                        "folder_id": folder_id,
                        "product_id": product_id,
                        "version_id": version_id,
                        "thumbnail_id": thumbnail_id,
                    }
                )
        self._selected_versions_info = selected_versions_info
        self._selected_merged_products = []
        project_name = self._controller.get_selected_project_name()
        if project_name and selected_version_ids:
            self._drag_precache.pre_build(
                self._controller,
                project_name,
                selected_version_ids,
                "version",
            )
        self._controller.set_selected_versions(selected_version_ids)
        self._sync_card_selection_chrome()
        self.selection_changed.emit()
        self.merged_products_selection_changed.emit()

    def get_selected_version_info(self) -> List[dict]:
        return list(self._selected_versions_info)

    def get_selected_merged_products(self) -> List[dict]:
        return list(self._selected_merged_products)

    def eventFilter(self, obj, event):
        if obj is self._list_view.viewport() and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        ):
            self._schedule_index_widget_geometry_sync()
        if obj is self._list_view.viewport() and event.type() == QtCore.QEvent.Type.Wheel:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta != 0:
                    self.scale_change_requested.emit(1 if delta > 0 else -1)
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def set_selection_from_version_ids(self, version_ids: set) -> None:
        """Sync grid selection from external (e.g. list) selection."""
        sm = self._list_view.selectionModel()
        sm.blockSignals(True)
        try:
            sm.clearSelection()
            for row in range(self._flatten_proxy.rowCount()):
                idx = self._flatten_proxy.index(row, 0)
                if idx.data(VERSION_ID_ROLE) in version_ids:
                    sm.select(
                        idx,
                        QtCore.QItemSelectionModel.SelectionFlag.Select,
                    )
        finally:
            sm.blockSignals(False)
        self._on_selection_changed()
