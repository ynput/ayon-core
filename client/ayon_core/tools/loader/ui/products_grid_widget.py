"""Grid view of products: web-style cards with thumbnail, version combo, review link."""

# ruff: noqa: E501
from __future__ import annotations

import collections
import numbers
from typing import Any, Dict, List, Optional, Set

LOADER_QSETTINGS_GROUP = "loader"

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib import Logger
from ayon_core.tools.utils.lib import format_version

from .products_flatten_proxy import (
    GRID_ROW_IS_HEADER_ROLE,
    GRID_SECTION_GROUP_KEY_ROLE,
    ProductsFlattenProxyModel,
    build_unified_grid_flat_rows,
    enumerate_grid_section_source_indexes,
)
from .products_grid_card_widget import (
    CARD_BASE_HEIGHT,
    CARD_BASE_WIDTH,
    GRID_SECTION_HEADER_ROW_HEIGHT,
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

# Defer IconMode index-widget creation until the scroll viewport has a stable
# size (Qt can glitch on a zero-sized transient layout). Thresholds stay low
# so a narrow splitter column still qualifies.
GRID_READY_MIN_VIEWPORT_W = 80
GRID_READY_MIN_VIEWPORT_H = 60
GRID_DEFER_REBUILD_MS = 50
_DEFER_REBUILD_MAX_POLLS = 40
GRID_VIEW_MARGIN_MIN_PX = 8
GRID_CONTENT_TOP_OFFSET_PX = 10
GRID_CONTENT_RIGHT_NUDGE_PX = 4

# Sender token for ``ProductsModel`` representation refresh (must match control).
_GRID_THUMB_SENDER = "loader.grid_thumbnail"

# QSettings: collapsed section keys (comma-separated under LOADER_SETTINGS_GROUP).
_GRID_SECTION_COLLAPSED_KEY = "GridSectionCollapsedKeys"


def columns_from_density_scale(scale: float) -> int:
    """Map legacy 0.5–2.0 view scale to a column count (fewer columns when scale is high)."""
    s = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
    span = GRID_COLUMNS_MAX - GRID_COLUMNS_MIN
    u = (s - MIN_SCALE) / (MAX_SCALE - MIN_SCALE)
    return int(round(GRID_COLUMNS_MAX - u * span))


DEFAULT_GRID_COLUMNS = 5

_log = Logger.get_logger("loader.ProductsGridWidget")


class GridSectionHeaderWidget(QtWidgets.QWidget):
    """One titled band for a product group (same grouping as list tree)."""

    def __init__(
        self,
        grid: "ProductsGridWidget",
        title: str,
        group_key: str,
        product_count: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._grid = grid
        self._group_key = group_key
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 4)
        outer.setSpacing(8)
        self._btn = QtWidgets.QToolButton(self)
        self._btn.setAutoRaise(True)
        self._btn.setStyleSheet("QToolButton { border: none; }")
        self._btn.clicked.connect(self._on_disclosure_clicked)
        self._title = QtWidgets.QLabel(title, self)
        self._title.setStyleSheet("font-weight: 600; color: #dbe0e6;")
        self._count = QtWidgets.QLabel(f"({product_count})", self)
        self._count.setStyleSheet("color: #9aa1aa;")
        outer.addWidget(self._btn, 0)
        outer.addWidget(self._title, 1)
        outer.addWidget(self._count, 0)
        self._sync_arrow()

    def _sync_arrow(self) -> None:
        expanded = self._grid.is_section_expanded(self._group_key)
        self._btn.setArrowType(
            QtCore.Qt.ArrowType.DownArrow
            if expanded
            else QtCore.Qt.ArrowType.RightArrow
        )

    def _on_disclosure_clicked(self) -> None:
        expanded = self._grid.is_section_expanded(self._group_key)
        self._grid.set_section_expanded(self._group_key, not expanded)
        self._grid.schedule_rebuild_grid_sections()


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
        flatten_proxy.set_controller(controller)
        flatten_proxy.set_auto_rebuild_from_source(False)
        self._proxy_model = flatten_proxy.sourceModel()
        self._collapsed_section_keys: Set[str] = set()
        self._section_product_counts: Dict[str, int] = {}
        self._load_collapsed_section_keys_from_settings()
        self._thumbnail_path_by_card_key: Dict[tuple[str, str], Optional[str]] = {}
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
        self._defer_rebuild_poll_count = 0
        self._grid_sections_rebuild_pending = False
        self._syncing_index_widget_geometries = False
        self._index_widget_geometry_sync_queued = False
        self._grid_content_offset_x = 0
        self._grid_content_offset_y = 0

        self._last_thumb_project: Optional[str] = None
        self._thumb_viewport_timer = QtCore.QTimer(self)
        self._thumb_viewport_timer.setSingleShot(True)
        self._thumb_viewport_timer.setInterval(120)
        self._thumb_viewport_timer.timeout.connect(
            self._run_viewport_thumbnail_refresh
        )
        self._thumb_drip_timer = QtCore.QTimer(self)
        self._thumb_drip_timer.setSingleShot(True)
        self._thumb_drip_timer.setInterval(120)
        self._thumb_drip_timer.timeout.connect(self._run_thumbnail_drip)

        self._scroll_area = QtWidgets.QScrollArea(self)
        self._scroll_area.setObjectName("ProductsGridScrollArea")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._grid_host = QtWidgets.QWidget(self._scroll_area)
        self._grid_host.setObjectName("ProductsGridHost")
        grid_host_layout = QtWidgets.QVBoxLayout(self._grid_host)
        grid_host_layout.setContentsMargins(0, 0, 0, 0)
        grid_host_layout.setSpacing(0)
        self._list_view = self._create_grid_list_view(self._grid_host)
        grid_host_layout.addWidget(self._list_view, 1)
        self._scroll_area.setWidget(self._grid_host)

        self._list_view.setModel(self._flatten_proxy)
        self._list_view.setItemDelegate(GridCellDelegate(self, self._list_view))
        sel_model = self._list_view.selectionModel()
        if sel_model is not None:
            sel_model.selectionChanged.connect(self._on_selection_changed)
        self._list_view.customContextMenuRequested.connect(
            self._on_grid_context_menu
        )
        self._list_view.viewport().installEventFilter(self)
        self._scroll_area.viewport().installEventFilter(self)

        self._grid_bottom_spacer = QtWidgets.QWidget(self)
        self._grid_bottom_spacer.setFixedHeight(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll_area, 1)
        layout.addWidget(self._grid_bottom_spacer, 0)

        self._controller.grid_thumbnail_ready.connect(
            self._on_grid_thumbnail_ready,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )

        if self._proxy_model is not None:
            self._proxy_model.modelReset.connect(self.schedule_rebuild_grid_sections)
            self._proxy_model.layoutChanged.connect(self.schedule_rebuild_grid_sections)
            self._proxy_model.rowsInserted.connect(self.schedule_rebuild_grid_sections)
            self._proxy_model.rowsRemoved.connect(self.schedule_rebuild_grid_sections)
            self._proxy_model.dataChanged.connect(self._on_proxy_data_changed)

        self._apply_grid_chrome_background()
        self._drag_precache = DragPayloadPrecache()

        self._rebuild_grid_sections()

    def products_proxy_model(self):
        """Products proxy (filters/sort) shared with list view."""
        return self._flatten_proxy.sourceModel()

    def schedule_rebuild_grid_sections(self, *_args) -> None:
        """Rebuild sections once after structural proxy updates.

        ``QStandardItemModel`` loads typically emit ``rowsInserted`` /
        ``rowsRemoved`` without ``layoutChanged``. Without listening for those,
        the grid stayed empty after the initial empty ``_rebuild_grid_sections``
        in ``__init__``.
        """
        if self._grid_sections_rebuild_pending:
            return
        self._grid_sections_rebuild_pending = True
        QtCore.QTimer.singleShot(0, self._flush_scheduled_rebuild_grid_sections)

    def _flush_scheduled_rebuild_grid_sections(self) -> None:
        self._grid_sections_rebuild_pending = False
        self._rebuild_grid_sections()

    @staticmethod
    def _card_thumb_key(product_id: str, version_id: str) -> tuple[str, str]:
        return (product_id, version_id)

    def _collect_product_version_pairs(self) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            if idx.data(GRID_ROW_IS_HEADER_ROLE):
                continue
            vid = idx.data(VERSION_ID_ROLE)
            pid = idx.data(PRODUCT_ID_ROLE)
            if vid and pid:
                pairs.append((str(pid), str(vid)))
        return pairs

    def _section_storage_key(self, title: Optional[str]) -> str:
        if title is None:
            return "__ungrouped__"
        return str(title)

    def _load_collapsed_section_keys_from_settings(self) -> None:
        settings = QtCore.QSettings()
        settings.beginGroup(LOADER_QSETTINGS_GROUP)
        raw = settings.value(_GRID_SECTION_COLLAPSED_KEY, "", type=str)
        settings.endGroup()
        if not raw or not isinstance(raw, str):
            self._collapsed_section_keys = set()
            return
        self._collapsed_section_keys = {
            k.strip() for k in raw.split(",") if k.strip()
        }

    def _persist_collapsed_section_keys(self) -> None:
        settings = QtCore.QSettings()
        settings.beginGroup(LOADER_QSETTINGS_GROUP)
        settings.setValue(
            _GRID_SECTION_COLLAPSED_KEY,
            ",".join(sorted(self._collapsed_section_keys)),
        )
        settings.endGroup()

    def is_section_expanded(self, group_key: str) -> bool:
        return group_key not in self._collapsed_section_keys

    def set_section_expanded(self, group_key: str, expanded: bool) -> None:
        if expanded:
            self._collapsed_section_keys.discard(group_key)
        else:
            self._collapsed_section_keys.add(group_key)
        self._persist_collapsed_section_keys()

    def _create_grid_list_view(self, parent) -> LoaderDragListView:
        """Single IconMode list: section headers + product tiles (variable row heights)."""
        lv = LoaderDragListView(parent)
        lv.setObjectName("ProductsGridView")
        lv.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        lv.setMovement(QtWidgets.QListView.Movement.Static)
        lv.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        lv.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        lv.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        lv.setUniformItemSizes(False)
        lv.setSpacing(0)
        lv.setSelectionRectVisible(True)
        lv.set_drag_data_callback(self._get_grid_drag_data)
        lv.set_drag_pixmap_context_callback(self._grid_drag_pixmap_context)
        lv.set_drag_precache(self._drag_precache)
        lv.verticalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )
        lv.verticalScrollBar().valueChanged.connect(
            self._schedule_viewport_thumbnail_refresh
        )
        lv.horizontalScrollBar().valueChanged.connect(
            self._schedule_index_widget_geometry_sync
        )
        return lv

    def _rebuild_grid_sections(self) -> None:
        """Rebuild unified flat model (section headers + products) from proxy tree."""
        self._controller.cancel_grid_thumbnail_resolve()
        self._thumbnail_path_by_card_key.clear()
        self._last_thumb_project = None

        proxy = self.products_proxy_model()
        if proxy is None:
            self._flatten_proxy.set_explicit_flat_rows([])
            self._schedule_index_widget_geometry_sync()
            return

        specs = enumerate_grid_section_source_indexes(proxy)
        self._section_product_counts = {
            self._section_storage_key(title): len(indexes)
            for title, indexes in specs
            if title is not None and indexes
        }
        rows = build_unified_grid_flat_rows(
            proxy,
            collapsed_group_keys=self._collapsed_section_keys,
        )
        self._flatten_proxy.set_explicit_flat_rows(rows)

        self._ensure_products_model_signals()
        self._apply_grid_geometry()
        self._rebuild_index_widgets()
        if self._total_product_row_count() > 0:
            QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)

    def _total_flat_row_count(self) -> int:
        """All proxy rows (headers + products)."""
        return int(self._flatten_proxy.rowCount())

    def _total_product_row_count(self) -> int:
        n = 0
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            ix = fp.index(row, 0)
            if ix.data(PRODUCT_ID_ROLE) is not None:
                n += 1
        return n

    def _on_proxy_data_changed(
        self,
        top_left: QtCore.QModelIndex,
        bottom_right: QtCore.QModelIndex,
        roles=None,
    ) -> None:
        _ = (top_left, bottom_right, roles)
        lv = self._list_view
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            if idx.data(GRID_ROW_IS_HEADER_ROLE):
                continue
            w = lv.indexWidget(idx)
            if isinstance(w, ProductsGridCardWidget):
                w.refresh_from_model()

    @property
    def list_view(self) -> LoaderDragListView:
        """Unified IconMode list (section bands + product tiles)."""
        return self._list_view

    def _grid_drag_pixmap_context(self):
        """Labels + cached thumbnail path for composite drag pixmap."""
        data = self._get_grid_drag_data()
        if not data:
            return None
        project_name, version_ids, _ = data
        ix = None
        model = None
        sm = self._list_view.selectionModel()
        if sm is not None:
            sel = sm.selectedIndexes()
            if sel:
                ix = sel[0]
                model = self._list_view.model()
        thumb_path = None
        if ix is not None and ix.isValid() and model is not None:
            pid = model.data(ix, PRODUCT_ID_ROLE)
            vid = model.data(ix, VERSION_ID_ROLE)
            if pid and vid:
                thumb_path = self.get_thumbnail_path(str(pid), str(vid))
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
        version_ids = set()
        selection_model = self._list_view.selectionModel()
        model = self._list_view.model()
        if selection_model is None or model is None:
            return None
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
        """#1c2026 behind scroll area + viewport."""
        fill = QtGui.QColor("#1c2026")
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, fill)
        self.setPalette(pal)
        self._scroll_area.setAutoFillBackground(True)
        sap = self._scroll_area.palette()
        sap.setColor(QtGui.QPalette.Window, fill)
        self._scroll_area.setPalette(sap)
        vp = self._scroll_area.viewport()
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
        """Usable drawable width for column math (grid list viewport)."""
        vp = self._list_view.viewport()
        inner_raw = max(1, vp.width())
        vsb = self._list_view.verticalScrollBar()
        if vsb is not None and not vsb.isVisible():
            sb_ext = self._list_view.style().pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent,
                None,
                self._list_view,
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
        """Grid tile size from thumb-only aspect; apply to the unified list view."""
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

        self._cached_tile = tile_size_for_cell_width(tw_final)
        tile_h = self._cached_tile.height()
        self._grid_stride = QtCore.QSize(stride_w, tile_h + sp_layout)
        row_w = self._grid_columns * self._grid_stride.width()
        self._grid_content_offset_x = max(
            GRID_VIEW_MARGIN_MIN_PX,
            (inner - row_w) // 2,
        ) + GRID_CONTENT_RIGHT_NUDGE_PX
        self._grid_content_offset_y = GRID_CONTENT_TOP_OFFSET_PX

        lv = self._list_view
        lv.setSpacing(0)
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
            self._defer_rebuild_poll_count = 0
            self._rebuild_index_widgets()
            if self._total_product_row_count() > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)
            return
        if prev != self._cached_tile:
            self._rebuild_index_widgets()
            if self._total_product_row_count() > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)
        else:
            self._sync_index_widget_geometries()
            self._scroll_area.viewport().update()

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
            self._scroll_area.viewport().update()
        self._schedule_viewport_thumbnail_refresh()

    def set_scale_factor(self, value: float) -> None:
        """Legacy adapter: maps old 0.5–2.0 density scale to column count once."""
        self.set_grid_columns(columns_from_density_scale(value))

    def get_thumbnail_path(
        self,
        product_id: Optional[str],
        version_id: Optional[str],
    ) -> Optional[str]:
        if not product_id or not version_id:
            return None
        return self._thumbnail_path_by_card_key.get(
            self._card_thumb_key(str(product_id), str(version_id))
        )

    def _sync_project_thumb_cache(self, project_name: Optional[str]) -> None:
        if project_name == self._last_thumb_project:
            return
        self._controller.cancel_grid_thumbnail_resolve()
        self._thumbnail_path_by_card_key.clear()
        self._last_thumb_project = project_name

    def _all_version_ids(self) -> Set[str]:
        out: Set[str] = set()
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            vid = fp.index(row, 0).data(VERSION_ID_ROLE)
            if vid:
                out.add(vid)
        return out

    def _visible_version_ids(self) -> Set[str]:
        out: Set[str] = set()
        lv = self._list_view
        vp = lv.viewport()
        fp = self._flatten_proxy
        rc = fp.rowCount()
        if rc == 0:
            return out
        top_idx = lv.indexAt(QtCore.QPoint(0, 0))
        bottom_idx = lv.indexAt(
            QtCore.QPoint(max(0, vp.width() - 1), max(0, vp.height() - 1))
        )
        if not top_idx.isValid():
            return out
        r0 = max(0, top_idx.row() - 1)
        if bottom_idx.isValid():
            r1 = bottom_idx.row()
        else:
            r1 = rc - 1
        r1 = min(rc - 1, r1 + 1)
        for row in range(r0, r1 + 1):
            vid = fp.index(row, 0).data(VERSION_ID_ROLE)
            if vid:
                out.add(vid)
        return out

    def _merge_resolve_paths(self, drip: bool) -> None:
        project_name = self._controller.get_selected_project_name()
        self._sync_project_thumb_cache(project_name)
        if not project_name:
            return

        if self._total_product_row_count() == 0:
            return

        all_pairs = self._collect_product_version_pairs()
        all_vids = self._all_version_ids()
        visible_vids = self._visible_version_ids()
        if drip:
            rest_vids = all_vids - visible_vids
            if not rest_vids:
                return
            pairs = [p for p in all_pairs if p[1] in rest_vids]
            target_vids = rest_vids
        else:
            vpairs = [p for p in all_pairs if p[1] in visible_vids]
            if vpairs:
                pairs = vpairs
                target_vids = {p[1] for p in pairs}
            else:
                pairs = all_pairs
                target_vids = all_vids

        if not pairs or not target_vids:
            return

        sync_map = self._controller.resolve_grid_thumbnail_paths(
            project_name,
            target_vids,
            sender=_GRID_THUMB_SENDER,
            product_version_pairs=pairs,
        )
        for key, path in sync_map.items():
            if path:
                self._thumbnail_path_by_card_key[key] = path

        if not drip:
            self._thumb_drip_timer.start()

    def _schedule_viewport_thumbnail_refresh(self, *_args) -> None:
        self._thumb_viewport_timer.start()

    def _run_viewport_thumbnail_refresh(self) -> None:
        self._merge_resolve_paths(drip=False)

    def _run_thumbnail_drip(self) -> None:
        self._merge_resolve_paths(drip=True)

    def _on_grid_thumbnail_ready(
        self, product_id: str, version_id: str, path: str
    ) -> None:
        if not self._is_grid_viewport_ready_for_cards():
            return
        key = self._card_thumb_key(product_id, version_id)
        self._thumbnail_path_by_card_key[key] = path
        fp = self._flatten_proxy
        lv = self._list_view
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            if idx.data(VERSION_ID_ROLE) != version_id:
                continue
            if idx.data(PRODUCT_ID_ROLE) != product_id:
                continue
            w = lv.indexWidget(idx)
            if isinstance(w, ProductsGridCardWidget):
                w._thumb.update()

    def _ensure_products_model_signals(self) -> None:
        pm = self.products_model()
        if pm is None or self._version_changed_connected:
            return
        pm.version_changed.connect(self._on_products_model_version_changed)
        self._version_changed_connected = True

    def _on_products_model_version_changed(self) -> None:
        self._update_thumbnail_cache()
        self._refresh_all_cards()

    def _update_thumbnail_cache(self) -> None:
        self._thumb_viewport_timer.stop()
        self._thumb_drip_timer.stop()
        self._merge_resolve_paths(drip=False)

    def _scroll_grid_to_top_deferred(self) -> None:
        vsb = self._scroll_area.verticalScrollBar()
        if vsb is not None:
            vsb.setValue(0)
        lv = self._list_view
        idx = lv.model().index(0, 0)
        if idx.isValid():
            lv.scrollTo(
                idx,
                QtWidgets.QAbstractItemView.ScrollHint.PositionAtTop,
            )
        self._sync_index_widget_geometries()

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
        self._defer_rebuild_poll_count = 0
        QtCore.QTimer.singleShot(
            GRID_DEFER_REBUILD_MS,
            self._run_deferred_rebuild_index_widgets,
        )

    def _run_deferred_rebuild_index_widgets(self) -> None:
        if not self._rebuild_index_widgets_deferred:
            return
        row_count = self._flatten_proxy.rowCount()
        ready = self._is_grid_viewport_ready_for_cards()
        if row_count > 0 and not ready:
            self._defer_rebuild_poll_count += 1
            if self._defer_rebuild_poll_count < _DEFER_REBUILD_MAX_POLLS:
                QtCore.QTimer.singleShot(
                    GRID_DEFER_REBUILD_MS,
                    self._run_deferred_rebuild_index_widgets,
                )
                return
        self._rebuild_index_widgets_deferred = False
        self._defer_rebuild_poll_count = 0
        relax = row_count > 0 and not ready
        self._rebuild_index_widgets(relax_viewport_ready=relax)

    def _try_flush_deferred_index_widgets(self) -> None:
        """Run deferred card build once the scroll viewport has a real geometry."""
        if not self._rebuild_index_widgets_deferred:
            return
        if self._flatten_proxy.rowCount() == 0:
            self._rebuild_index_widgets_deferred = False
            self._defer_rebuild_poll_count = 0
            return
        if not self._is_grid_viewport_ready_for_cards():
            return
        self._rebuild_index_widgets_deferred = False
        self._defer_rebuild_poll_count = 0
        self._rebuild_index_widgets()

    def _rebuild_index_widgets(self, relax_viewport_ready: bool = False) -> None:
        if self._rebuilding_index_widgets:
            return
        row_count = self._flatten_proxy.rowCount()
        if (
            row_count > 0
            and not relax_viewport_ready
            and not self._is_grid_viewport_ready_for_cards()
        ):
            self._apply_grid_geometry()
            self._schedule_deferred_rebuild_index_widgets()
            return
        self._apply_grid_geometry()
        tile = self._tile_size()
        w, h = tile.width(), tile.height()
        fp = self._flatten_proxy
        lv = self._list_view
        vp = lv.viewport()
        vpw = max(1, vp.width())
        self._rebuilding_index_widgets = True
        try:
            for row in range(fp.rowCount()):
                idx = fp.index(row, 0)
                if not idx.isValid():
                    continue
                existing = lv.indexWidget(idx)
                if idx.data(GRID_ROW_IS_HEADER_ROLE):
                    title = str(idx.data(QtCore.Qt.DisplayRole) or "")
                    gkey = str(idx.data(GRID_SECTION_GROUP_KEY_ROLE) or "")
                    count = int(self._section_product_counts.get(gkey, 0))
                    hdr = GridSectionHeaderWidget(
                        self, title, gkey, count, vp
                    )
                    hdr.setFixedSize(vpw, GRID_SECTION_HEADER_ROW_HEIGHT)
                    lv.setIndexWidget(idx, hdr)
                    hdr.raise_()
                    continue
                if isinstance(existing, ProductsGridCardWidget):
                    existing._flat_row = row
                    existing.setFixedSize(w, h)
                    existing.refresh_from_model()
                else:
                    card = ProductsGridCardWidget(self, row, vp)
                    card.setFixedSize(w, h)
                    lv.setIndexWidget(idx, card)
                    card.refresh_from_model()
                    card.raise_()
        except BaseException:
            _log.exception("grid index-widget rebuild")
            raise
        finally:
            self._rebuilding_index_widgets = False
            if row_count > 0:
                lv.updateGeometries()
                self._sync_index_widget_geometries()
            self._sync_card_selection_chrome()
            if row_count > 0:
                QtCore.QTimer.singleShot(0, self._scroll_grid_to_top_deferred)

    def _refresh_all_cards(self) -> None:
        lv = self._list_view
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            if idx.data(GRID_ROW_IS_HEADER_ROLE):
                continue
            w = lv.indexWidget(idx)
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
            lv = self._list_view
            fp = self._flatten_proxy
            for row in range(fp.rowCount()):
                idx = fp.index(row, 0)
                if not idx.isValid():
                    continue
                wgt = lv.indexWidget(idx)
                rect = lv.visualRect(idx)
                if not rect.isValid():
                    continue
                top_left = rect.topLeft() + QtCore.QPoint(
                    self._grid_content_offset_x,
                    self._grid_content_offset_y,
                )
                if isinstance(wgt, GridSectionHeaderWidget):
                    geom = QtCore.QRect(
                        top_left,
                        QtCore.QSize(
                            max(rect.width(), 1),
                            max(rect.height(), GRID_SECTION_HEADER_ROW_HEIGHT),
                        ),
                    )
                elif isinstance(wgt, ProductsGridCardWidget):
                    geom = QtCore.QRect(top_left, tile)
                else:
                    continue
                if wgt.geometry() != geom:
                    wgt.setGeometry(geom)
                if not wgt.isVisible():
                    wgt.show()
                wgt.raise_()
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
        lv = self._list_view
        fp = self._flatten_proxy
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            if idx.data(GRID_ROW_IS_HEADER_ROLE):
                continue
            w = lv.indexWidget(idx)
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
        lv = self._list_view
        sm = lv.selectionModel()
        if sm is None:
            return
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Toggle)
        else:
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
        lv.setCurrentIndex(idx)

    def open_context_menu_from_card(
        self,
        global_pos: QtCore.QPoint,
        flat_row: int,
    ) -> None:
        """Card chrome RMB: select row then open loader menu."""
        idx = self._flatten_proxy.index(flat_row, 0)
        if not idx.isValid():
            return
        lv = self._list_view
        sm = lv.selectionModel()
        if sm is None:
            return
        if not sm.isSelected(idx):
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
            lv.setCurrentIndex(idx)
        self._run_context_menu_at_global(global_pos)

    def _on_grid_context_menu(self, point: QtCore.QPoint) -> None:
        lv = self._list_view
        sm = lv.selectionModel()
        if sm is not None and not lv.selectedIndexes():
            idx = lv.indexAt(point)
            if idx.isValid() and not idx.data(GRID_ROW_IS_HEADER_ROLE):
                sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
                lv.setCurrentIndex(idx)
        self._run_context_menu_at_global(lv.viewport().mapToGlobal(point))

    def _run_context_menu_at_global(self, global_point: QtCore.QPoint) -> None:
        project_name = self._controller.get_selected_project_name()
        version_ids = set()
        indexes_queue = collections.deque()
        sm = self._list_view.selectionModel()
        if sm is not None:
            indexes_queue.extend(sm.selectedIndexes())
        while indexes_queue:
            index = indexes_queue.popleft()
            model = index.model()
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
        lv = self._list_view
        fp = self._flatten_proxy
        sm = lv.selectionModel()
        if sm is None:
            return
        for row in range(fp.rowCount()):
            idx = fp.index(row, 0)
            w = lv.indexWidget(idx)
            if isinstance(w, ProductsGridCardWidget):
                w.set_grid_row_selected(idx.isValid() and sm.isSelected(idx))

    def _on_selection_changed(self) -> None:
        selected_version_ids = set()
        selected_versions_info = []
        sm = self._list_view.selectionModel()
        if sm is None:
            return
        for idx in sm.selectedIndexes():
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
        self._controller.set_selected_versions(
            selected_version_ids, selected_versions_info
        )
        self._sync_card_selection_chrome()
        self.selection_changed.emit()
        self.merged_products_selection_changed.emit()

    def get_selected_version_info(self) -> List[dict]:
        return list(self._selected_versions_info)

    def get_selected_merged_products(self) -> List[dict]:
        return list(self._selected_merged_products)

    def eventFilter(self, obj, event):
        if event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        ):
            if obj is self._scroll_area.viewport() or obj is self._list_view.viewport():
                self._schedule_index_widget_geometry_sync()
                self._try_flush_deferred_index_widgets()
        if (
            obj is self._scroll_area.viewport()
            and event.type() == QtCore.QEvent.Type.Wheel
        ):
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
        if sm is None:
            return
        sm.blockSignals(True)
        try:
            sm.clearSelection()
            fp = self._flatten_proxy
            for row in range(fp.rowCount()):
                idx = fp.index(row, 0)
                if idx.data(GRID_ROW_IS_HEADER_ROLE):
                    continue
                if idx.data(VERSION_ID_ROLE) in version_ids:
                    sm.select(
                        idx,
                        QtCore.QItemSelectionModel.SelectionFlag.Select,
                    )
        finally:
            sm.blockSignals(False)
        self._on_selection_changed()
