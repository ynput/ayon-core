"""Grid view of products: web-style cards with thumbnail, version combo, review link."""
from __future__ import annotations

import collections
import numbers
from typing import Any, Callable, Dict, List, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.utils.lib import format_version

from .products_flatten_proxy import ProductsFlattenProxyModel
from .products_proxy_selection import (
    collect_version_ids_from_column0_indexes,
    find_root_group_column0_index,
)
from .products_grid_card_widget import (
    CARD_BASE_HEIGHT,
    CARD_BASE_WIDTH,
    tile_size_for_cell_width,
)
from .products_grid_geometry import (
    DEFAULT_GRID_COLUMNS,
    GRID_CELL_SPACING,
    GRID_COLUMNS_MAX,
    GRID_COLUMNS_MIN,
    GRID_CONTENT_RIGHT_NUDGE_PX,
    GRID_CONTENT_TOP_OFFSET_PX,
    GRID_ROW_WRAP_SAFETY_PX,
    GRID_VIEW_MARGIN_MIN_PX,
    MIN_CELL_WIDTH,
    columns_from_density_scale,
    compute_column_bounds_for_inner,
)
from .products_model import (
    FOLDER_ID_ROLE,
    GROUP_NAME_ROLE,
    PRODUCT_ID_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_ID_ROLE,
    VERSION_NAME_ROLE,
    VERSION_THUMBNAIL_ID_ROLE,
)
from .products_delegates import VersionComboBox
from .products_grid_constants import grid_view_surface_color
from .products_grid_section import ProductsGridSection
from .actions_utils import DragPayloadPrecache, show_actions_menu

# Re-export for scale_slider_overlay / window.
__all__ = [
    "ProductsGridWidget",
    "DEFAULT_GRID_COLUMNS",
    "GRID_COLUMNS_MIN",
    "GRID_COLUMNS_MAX",
    "columns_from_density_scale",
]

_log = Logger.get_logger("loader.ProductsGridWidget")


class ProductsGridWidget(QtWidgets.QWidget):
    """Grid of product cards in grouped sections; drives same controller signals."""

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

        self._grid_content_offset_x = 0
        self._grid_content_offset_y = GRID_CONTENT_TOP_OFFSET_PX

        self._sections: Dict[Optional[str], ProductsGridSection] = {}
        self._section_order_keys: List[Optional[str]] = []
        self._list_view_to_section: Dict[QtWidgets.QListView, ProductsGridSection] = {}
        self._collapsed_groups: set[str] = set()
        self._suppress_selection_broadcast = False
        self._active_source_drag_list_view: Optional[QtWidgets.QListView] = None
        self._marquee_backup_before_source_drag: Dict[int, bool] = {}

        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.viewport().setAutoFillBackground(True)

        self._content_widget = QtWidgets.QWidget(self._scroll)
        self._content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content_widget)

        self._grid_bottom_spacer = QtWidgets.QWidget(self)
        self._grid_bottom_spacer.setFixedHeight(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._grid_bottom_spacer, 0)

        self._flatten_proxy.modelReset.connect(self._on_flatten_model_reset)
        self._flatten_proxy.layoutChanged.connect(self._on_flatten_layout_changed)
        self._flatten_proxy.rowsInserted.connect(self._on_rows_changed)
        self._flatten_proxy.rowsRemoved.connect(self._on_rows_changed)
        self._flatten_proxy.dataChanged.connect(self._on_flat_data_changed)

        self._apply_grid_chrome_background()
        self._scroll.viewport().installEventFilter(self)

        self._drag_precache = DragPayloadPrecache()

        self._sync_sections_with_model()
        self._apply_grid_geometry()
        self._ensure_products_model_signals()
        self._update_thumbnail_cache()
        self._refresh_all_sections_cards()
        self.apply_delegate_filters_to_group_headers()

    @property
    def drag_precache(self) -> DragPayloadPrecache:
        return self._drag_precache

    def register_active_source_drag_list_view(
        self, list_view: QtWidgets.QListView
    ) -> None:
        if self._active_source_drag_list_view is not None:
            return
        self._active_source_drag_list_view = list_view
        self._suppress_marquee_for_source_drag()

    def _suppress_marquee_for_source_drag(self) -> None:
        """Hide rubber-band on every section list for the whole drag gesture."""
        self._marquee_backup_before_source_drag.clear()
        for sec in self._sections_in_display_order():
            lv = sec.list_view
            key = id(lv)
            self._marquee_backup_before_source_drag[key] = bool(
                lv.isSelectionRectVisible()
            )
            lv.setSelectionRectVisible(False)

    def _restore_marquee_after_source_drag(self) -> None:
        for sec in self._sections_in_display_order():
            lv = sec.list_view
            key = id(lv)
            prev = self._marquee_backup_before_source_drag.pop(key, True)
            try:
                lv.setSelectionRectVisible(prev)
            except RuntimeError:
                pass
        self._marquee_backup_before_source_drag.clear()

    def clear_active_source_drag_list_view(
        self, list_view: QtWidgets.QListView
    ) -> None:
        if self._active_source_drag_list_view is not list_view:
            return
        self._active_source_drag_list_view = None
        self._restore_marquee_after_source_drag()

    @property
    def list_view(self) -> Optional[QtWidgets.QAbstractItemView]:
        """First section list (legacy); grid uses multiple QListViews."""
        if not self._section_order_keys:
            return None
        first_key = self._section_order_keys[0]
        sec = self._sections.get(first_key)
        return sec.list_view if sec else None

    def card_model(self):
        """First section proxy (unused by cards; sections host models)."""
        if not self._section_order_keys:
            return self._flatten_proxy
        sec = self._sections.get(self._section_order_keys[0])
        return sec.card_model() if sec else self._flatten_proxy

    def _scroll_viewport_inner_width(self) -> int:
        return max(1, self._scroll.viewport().width())

    def get_grid_content_offset_x(self) -> int:
        return int(self._grid_content_offset_x)

    def get_grid_content_offset_y(self) -> int:
        return int(self._grid_content_offset_y)

    def _ordered_group_keys(self) -> List[Optional[str]]:
        """Named groups first (first-seen order), ungrouped (`None`) last — matches list view."""
        named_order: List[str] = []
        named_seen: set[str] = set()
        has_ungrouped = False
        for row in range(self._flatten_proxy.rowCount()):
            k = self._flatten_proxy.index(row, 0).data(GROUP_NAME_ROLE)
            if k is None:
                has_ungrouped = True
            elif k not in named_seen:
                named_seen.add(k)
                named_order.append(k)
        ordered: List[Optional[str]] = list(named_order)
        if has_ungrouped:
            ordered.append(None)
        return ordered

    def _sections_in_display_order(self) -> List[ProductsGridSection]:
        return [self._sections[k] for k in self._section_order_keys if k in self._sections]

    def _sync_sections_with_model(self) -> None:
        ordered = self._ordered_group_keys()
        self._section_order_keys = list(ordered)

        for key in list(self._sections.keys()):
            if key not in ordered:
                sec = self._sections.pop(key)
                self._disconnect_section(sec)
                sec.deleteLater()

        for key in ordered:
            if key not in self._sections:
                show_header = key is not None
                sec = ProductsGridSection(self, key, show_header, self._content_widget)
                self._sections[key] = sec
                self._wire_section(sec)
                if key is not None:
                    self._collapsed_groups.add(key)

            sec = self._sections[key]
            if key is None:
                sec.set_section_expanded(True)
            else:
                sec.set_section_expanded(key not in self._collapsed_groups)

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(self._content_widget)

        for key in ordered:
            self._content_layout.addWidget(self._sections[key])
        self._content_layout.addStretch(1)

    def _wire_section(self, sec: ProductsGridSection) -> None:
        lv = sec.list_view
        self._list_view_to_section[lv] = sec
        sm = lv.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(
                lambda *_a, s=sec: self._on_any_section_selection_changed(s)
            )

    def _disconnect_section(self, sec: ProductsGridSection) -> None:
        lv = sec.list_view
        self._list_view_to_section.pop(lv, None)
        sm = lv.selectionModel()
        if sm is not None:
            try:
                sm.selectionChanged.disconnect()
            except TypeError:
                pass

    def on_section_header_toggled(self, section: ProductsGridSection, expanded: bool) -> None:
        gk = section.group_key
        if gk is not None:
            if expanded:
                self._collapsed_groups.discard(gk)
            else:
                self._collapsed_groups.add(gk)
        if expanded:
            self.refresh_section_cards(section)

    def refresh_section_cards(self, section: ProductsGridSection) -> None:
        section.refresh_cards()

    def sync_section_selection_chrome(self, section: ProductsGridSection) -> None:
        sm = section.list_view.selectionModel()
        if sm is None:
            return
        model = section.card_model()
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            w = section.list_view.indexWidget(idx)
            if hasattr(w, "set_grid_row_selected"):
                w.set_grid_row_selected(idx.isValid() and sm.isSelected(idx))

    def open_context_menu_from_section_list(self, point: QtCore.QPoint) -> None:
        lv = self.sender()
        if not isinstance(lv, QtWidgets.QListView):
            return
        sec = self._list_view_to_section.get(lv)
        if sec is None:
            return
        idx = lv.indexAt(point)
        sm = lv.selectionModel()
        if sm is not None and not lv.selectedIndexes():
            if idx.isValid():
                sm.clearSelection()
                sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
                lv.setCurrentIndex(idx)
        vp = lv.viewport()
        self._run_context_menu_at_global(vp.mapToGlobal(point))

    def open_context_menu_from_section_card(
        self,
        section: ProductsGridSection,
        global_pos: QtCore.QPoint,
        flat_row: int,
    ) -> None:
        idx = section.card_model().index(flat_row, 0)
        if not idx.isValid():
            return
        sm = section.list_view.selectionModel()
        if not sm.isSelected(idx):
            sm.clearSelection()
            sm.select(idx, QtCore.QItemSelectionModel.SelectionFlag.Select)
            section.list_view.setCurrentIndex(idx)
        self._run_context_menu_at_global(global_pos)

    def get_section_drag_data_builder(self, section: ProductsGridSection) -> Callable:
        def build():
            return self._drag_data_for_list(section.list_view, section.card_model())

        return build

    def get_section_drag_pixmap_builder(self, section: ProductsGridSection) -> Callable:
        def build():
            return self._drag_pixmap_context_for_list(section.list_view, section.card_model())

        return build

    def section_viewport_wheel_event(self, event: QtGui.QWheelEvent) -> bool:
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                self.scale_change_requested.emit(1 if delta > 0 else -1)
                event.accept()
                return True
        return False

    def on_card_version_changed(self, product_id: str, version_id: str) -> None:
        pm = self.products_model()
        if pm:
            pm.set_product_version(product_id, version_id)

    def apply_filters_to_combo(self, combo: VersionComboBox) -> None:
        combo.set_tasks_filter(self._filter_task_ids)
        combo.set_statuses_filter(self._filter_status_names)
        combo.set_version_tags_filter(self._filter_version_tags)
        combo.set_task_tags_filter(self._filter_task_tags)

    def _drag_data_for_list(
        self,
        list_view: QtWidgets.QListView,
        model: QtCore.QAbstractItemModel,
    ):
        project_name = self._controller.get_selected_project_name()
        if not project_name:
            return None
        selection_model = list_view.selectionModel()
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

    def _drag_pixmap_context_for_list(
        self,
        list_view: QtWidgets.QListView,
        model: QtCore.QAbstractItemModel,
    ):
        data = self._drag_data_for_list(list_view, model)
        if not data:
            return None
        project_name, version_ids, _ = data
        vset = set(version_ids)
        first_vid = next(iter(version_ids))
        thumb_path = None
        pc = self.drag_precache.get(project_name, vset, "version")
        if pc:
            tbmap = pc.get("thumbnail_paths_by_version_id") or {}
            fk = str(first_vid)
            thumb_path = tbmap.get(fk) or tbmap.get(first_vid)
        if thumb_path is None:
            thumb_path = self._thumbnail_path_by_version_id.get(first_vid)
        indexes = list_view.selectionModel().selectedIndexes()
        ix = indexes[0] if indexes else None
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

    def _apply_grid_chrome_background(self) -> None:
        fill = grid_view_surface_color()
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, fill)
        self.setPalette(pal)
        vp = self._scroll.viewport()
        vp.setAutoFillBackground(True)
        vpal = vp.palette()
        vpal.setColor(QtGui.QPalette.Window, fill)
        vpal.setColor(QtGui.QPalette.Base, fill)
        vp.setPalette(vpal)
        self._content_widget.setAutoFillBackground(True)
        cw_pal = self._content_widget.palette()
        cw_pal.setColor(QtGui.QPalette.Window, fill)
        self._content_widget.setPalette(cw_pal)

    def get_tile_size(self) -> QtCore.QSize:
        return QtCore.QSize(self._cached_tile)

    def get_grid_stride_size(self) -> QtCore.QSize:
        return QtCore.QSize(self._grid_stride)

    def compute_column_bounds(self) -> tuple[int, int]:
        inner = self._scroll_viewport_inner_width()
        return compute_column_bounds_for_inner(inner)

    def get_column_bounds(self) -> tuple[int, int]:
        return (int(self._last_col_bounds[0]), int(self._last_col_bounds[1]))

    def _apply_grid_geometry(self) -> None:
        inner = self._scroll_viewport_inner_width()
        lo, hi = compute_column_bounds_for_inner(inner)
        self._last_col_bounds = (lo, hi)
        if self._emitted_col_bounds != (lo, hi):
            self._emitted_col_bounds = (lo, hi)
            self.column_bounds_changed.emit(lo, hi)

        start_cols = int(self._grid_columns)
        n = max(lo, min(hi, start_cols))
        sp = GRID_CELL_SPACING
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
        self._cached_tile = tile_size_for_cell_width(tw_final)
        tile_h = self._cached_tile.height()
        self._grid_stride = QtCore.QSize(stride_w, tile_h + sp)
        row_w = self._grid_columns * self._grid_stride.width()
        self._grid_content_offset_x = max(
            GRID_VIEW_MARGIN_MIN_PX,
            (inner - row_w) // 2,
        ) + GRID_CONTENT_RIGHT_NUDGE_PX
        self._grid_content_offset_y = GRID_CONTENT_TOP_OFFSET_PX

        for sec in self._sections_in_display_order():
            sec.apply_shared_geometry(
                inner,
                self._grid_columns,
                self._cached_tile,
                self._grid_stride,
                self._grid_content_offset_x,
                self._grid_content_offset_y,
            )

        QtCore.QTimer.singleShot(0, self._sync_all_section_geometries)

    def _sync_all_section_geometries(self) -> None:
        for sec in self._sections_in_display_order():
            sec._sync_index_widget_geometries()

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

    def products_proxy_model(self) -> Optional[QtCore.QAbstractItemModel]:
        return self._flatten_proxy.sourceModel()

    def drag_pixmap_context_for_proxy_column0_indexes(
        self,
        column0_indexes: List[QtCore.QModelIndex],
    ) -> Optional[dict]:
        project_name = self._controller.get_selected_project_name()
        if not project_name or not column0_indexes:
            return None
        pm = self.products_proxy_model()
        if pm is None:
            return None
        version_ids = collect_version_ids_from_column0_indexes(pm, column0_indexes)
        if not version_ids:
            return None
        vset = set(version_ids)
        first_vid = next(iter(version_ids))
        thumb_path = None
        pc = self.drag_precache.get(project_name, vset, "version")
        if pc:
            tbmap = pc.get("thumbnail_paths_by_version_id") or {}
            fk = str(first_vid)
            thumb_path = tbmap.get(fk) or tbmap.get(first_vid)
        if thumb_path is None:
            thumb_path = self._thumbnail_path_by_version_id.get(first_vid)
        ix = column0_indexes[0]
        product_label = ""
        version_label = ""
        if ix.isValid():
            product_label = str(pm.data(ix, PRODUCT_NAME_ROLE) or "")
            raw_ver = pm.data(ix, VERSION_NAME_ROLE)
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

    def open_group_header_context_menu(
        self, group_name: str, global_point: QtCore.QPoint
    ) -> None:
        pm = self.products_proxy_model()
        if pm is None:
            return
        ix = find_root_group_column0_index(pm, group_name)
        if not ix.isValid():
            return
        version_ids = collect_version_ids_from_column0_indexes(pm, [ix])
        project_name = self._controller.get_selected_project_name()
        if not project_name or not version_ids:
            return
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

    def apply_delegate_filters_to_group_headers(self) -> None:
        for sec in self._sections_in_display_order():
            sec.apply_header_delegate_filters(self)

    def get_scale_factor(self) -> float:
        return self._cached_tile.width() / float(CARD_BASE_WIDTH)

    def get_grid_columns(self) -> int:
        return int(self._grid_columns)

    def set_overlay_bottom_height(self, h: int) -> None:
        self._grid_bottom_spacer.setFixedHeight(max(0, int(h)))
        self._apply_grid_geometry()

    def set_grid_columns(self, n: int) -> None:
        prev_tile = QtCore.QSize(self._cached_tile)
        lo, hi = self._last_col_bounds
        self._grid_columns = max(lo, min(hi, int(n)))
        self._apply_grid_geometry()
        if prev_tile != self._cached_tile:
            self._refresh_all_sections_cards()
        else:
            self._sync_all_section_geometries()
            for sec in self._sections_in_display_order():
                sec.list_view.viewport().update()

    def set_scale_factor(self, value: float) -> None:
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
        self._refresh_all_cards_all_sections()

    def _on_flat_data_changed(
        self,
        top_left: QtCore.QModelIndex,
        bottom_right: QtCore.QModelIndex,
        roles=None,
    ) -> None:
        _ = top_left, bottom_right, roles
        self._refresh_all_cards_all_sections()

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
        self._sync_sections_with_model()
        self._apply_grid_geometry()
        self._refresh_all_sections_cards()

    def _scroll_sections_to_top_deferred(self) -> None:
        vsb = self._scroll.verticalScrollBar()
        if vsb is not None:
            vsb.setValue(0)
        self._sync_all_section_geometries()

    def _on_flatten_model_reset(self) -> None:
        self._refresh_grid_from_proxy()
        if self._flatten_proxy.rowCount() > 0:
            QtCore.QTimer.singleShot(0, self._scroll_sections_to_top_deferred)

    def _on_flatten_layout_changed(self) -> None:
        self._refresh_grid_from_proxy()

    def _on_rows_changed(self, *_args) -> None:
        self._ensure_products_model_signals()
        self._update_thumbnail_cache()
        self._sync_sections_with_model()
        self._apply_grid_geometry()
        self._refresh_all_sections_cards()

    def _refresh_all_sections_cards(self) -> None:
        for sec in self._sections_in_display_order():
            sec.refresh_cards()

    def _refresh_all_cards_all_sections(self) -> None:
        for sec in self._sections_in_display_order():
            sec.refresh_all_cards_from_model()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        prev = QtCore.QSize(self._cached_tile)
        self._apply_grid_geometry()
        if prev != self._cached_tile:
            self._refresh_all_sections_cards()
        else:
            self._sync_all_section_geometries()

    def _run_context_menu_at_global(self, global_point: QtCore.QPoint) -> None:
        project_name = self._controller.get_selected_project_name()
        version_ids = set()
        for sec in self._sections_in_display_order():
            sm = sec.list_view.selectionModel()
            model = sec.card_model()
            if sm is None:
                continue
            for idx in sm.selectedIndexes():
                if idx.column() != 0:
                    continue
                vid = model.data(idx, VERSION_ID_ROLE)
                if vid is not None:
                    version_ids.add(vid)

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
        for sec in self._sections_in_display_order():
            model = sec.card_model()
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                w = sec.list_view.indexWidget(idx)
                if hasattr(w, "version_combo") and w.version_combo:
                    self.apply_filters_to_combo(w.version_combo)
        self.apply_delegate_filters_to_group_headers()

    def select_flat_row(
        self,
        flat_row: int,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> None:
        """Select row in first section only (legacy single-grid API)."""
        if not self._section_order_keys:
            return
        sec = self._sections.get(self._section_order_keys[0])
        if sec:
            sec.select_flat_row(flat_row, modifiers)

    def _on_any_section_selection_changed(self, source_section: ProductsGridSection) -> None:
        if self._suppress_selection_broadcast:
            return
        mods = QtGui.QGuiApplication.keyboardModifiers()
        if not (mods & QtCore.Qt.KeyboardModifier.ControlModifier):
            self._suppress_selection_broadcast = True
            try:
                for sec in self._sections_in_display_order():
                    if sec is source_section:
                        continue
                    sm = sec.list_view.selectionModel()
                    if sm is not None:
                        sm.blockSignals(True)
                        sm.clearSelection()
                        sm.blockSignals(False)
            finally:
                self._suppress_selection_broadcast = False

        self._emit_aggregate_selection()

    def _emit_aggregate_selection(self) -> None:
        selected_version_ids = set()
        selected_versions_info = []
        for sec in self._sections_in_display_order():
            model = sec.card_model()
            for idx in sec.list_view.selectionModel().selectedIndexes():
                if idx.column() != 0:
                    continue
                if not idx.isValid():
                    continue
                version_id = model.data(idx, VERSION_ID_ROLE)
                product_id = model.data(idx, PRODUCT_ID_ROLE)
                folder_id = model.data(idx, FOLDER_ID_ROLE)
                thumbnail_id = model.data(idx, VERSION_THUMBNAIL_ID_ROLE)
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
            if _log:
                _log.debug(
                    "loader drag precache: selection-changed pn=%s n=%d "
                    "et=version",
                    project_name,
                    len(selected_version_ids),
                )
            self._drag_precache.pre_build(
                self._controller,
                project_name,
                selected_version_ids,
                "version",
            )
        self._controller.set_selected_versions(selected_version_ids)
        self._sync_all_selection_chrome()
        self.selection_changed.emit()
        self.merged_products_selection_changed.emit()

    def _sync_all_selection_chrome(self) -> None:
        for sec in self._sections_in_display_order():
            self.sync_section_selection_chrome(sec)

    def get_selected_version_info(self) -> List[dict]:
        return list(self._selected_versions_info)

    def get_selected_merged_products(self) -> List[dict]:
        return list(self._selected_merged_products)

    def eventFilter(self, obj, event):
        if obj is self._scroll.viewport() and event.type() == QtCore.QEvent.Type.Wheel:
            if self.section_viewport_wheel_event(event):
                return True
        return super().eventFilter(obj, event)

    def set_selection_from_version_ids(self, version_ids: set) -> None:
        self._suppress_selection_broadcast = True
        try:
            for sec in self._sections_in_display_order():
                sm = sec.list_view.selectionModel()
                model = sec.card_model()
                sm.blockSignals(True)
                try:
                    sm.clearSelection()
                    for row in range(model.rowCount()):
                        idx = model.index(row, 0)
                        if idx.data(VERSION_ID_ROLE) in version_ids:
                            sm.select(
                                idx,
                                QtCore.QItemSelectionModel.SelectionFlag.Select,
                            )
                finally:
                    sm.blockSignals(False)
        finally:
            self._suppress_selection_broadcast = False
        self._emit_aggregate_selection()
