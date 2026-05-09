"""Shared column / tile math for Loader product grid (list IconMode + index widgets)."""
from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

from qtpy import QtCore, QtWidgets

from .products_grid_card_widget import layout_dims_for_cell_width, tile_size_for_cell_width

MIN_SCALE = 0.5
MAX_SCALE = 2.0

GRID_COLUMNS_MIN = 3
GRID_COLUMNS_MAX = 12
DEFAULT_GRID_COLUMNS = 5

GRID_CELL_SPACING = 6
GRID_ROW_WRAP_SAFETY_PX = 6

GRID_VIEW_MARGIN_MIN_PX = 8
GRID_CONTENT_TOP_OFFSET_PX = 10
GRID_CONTENT_RIGHT_NUDGE_PX = 4

GRID_READY_MIN_VIEWPORT_W = 200
GRID_READY_MIN_VIEWPORT_H = 100
GRID_DEFER_REBUILD_MS = 50


def _min_cell_width_for_thumb_inner(min_inner: int = 90) -> int:
    from .products_grid_card_widget import CARD_BASE_WIDTH

    for tw in range(48, 600):
        if layout_dims_for_cell_width(tw)["inner_w"] >= min_inner:
            return tw
    return max(48, int(CARD_BASE_WIDTH * 0.65))


MIN_CELL_WIDTH = _min_cell_width_for_thumb_inner()


def columns_from_density_scale(scale: float) -> int:
    s = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
    span = GRID_COLUMNS_MAX - GRID_COLUMNS_MIN
    u = (s - MIN_SCALE) / (MAX_SCALE - MIN_SCALE)
    return int(round(GRID_COLUMNS_MAX - u * span))


def compute_column_bounds_for_inner(inner: int) -> Tuple[int, int]:
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


def viewport_inner_width_for_columns(list_view: QtWidgets.QListView) -> int:
    inner_raw = max(1, list_view.viewport().width())
    vsb = list_view.verticalScrollBar()
    if (
        vsb is not None
        and not vsb.isVisible()
        and list_view.verticalScrollBarPolicy()
        != QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    ):
        sb_ext = list_view.style().pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent, None, list_view
        )
        return max(1, inner_raw - sb_ext)
    return inner_raw


def apply_grid_geometry_to_view(
    list_view: QtWidgets.QListView,
    desired_columns: int,
    *,
    inner_width: Optional[int] = None,
    on_column_bounds_changed: Optional[Callable[[int, int], None]] = None,
) -> Tuple[int, QtCore.QSize, QtCore.QSize, int, int]:
    """Apply IconMode gridSize/iconSize. If inner_width is set, use it (shared outer width)."""
    if inner_width is not None:
        inner = max(1, int(inner_width))
    else:
        inner = viewport_inner_width_for_columns(list_view)
    lo, hi = compute_column_bounds_for_inner(inner)
    if on_column_bounds_changed is not None:
        on_column_bounds_changed(lo, hi)

    start_cols = int(desired_columns)
    n = max(lo, min(hi, start_cols))
    sp = GRID_CELL_SPACING
    stride_w = max(1, (inner // n) - GRID_ROW_WRAP_SAFETY_PX)
    tw = stride_w - sp
    while n > lo and tw < MIN_CELL_WIDTH:
        n -= 1
        stride_w = max(1, (inner // n) - GRID_ROW_WRAP_SAFETY_PX)
        tw = stride_w - sp

    effective_columns = n
    tw_final = tw

    list_view.setSpacing(0)
    cached_tile = tile_size_for_cell_width(tw_final)
    tile_h = cached_tile.height()
    grid_stride = QtCore.QSize(stride_w, tile_h + sp)
    row_w = effective_columns * grid_stride.width()
    offset_x = max(
        GRID_VIEW_MARGIN_MIN_PX,
        (inner - row_w) // 2,
    ) + GRID_CONTENT_RIGHT_NUDGE_PX
    offset_y = GRID_CONTENT_TOP_OFFSET_PX
    list_view.setViewportMargins(0, 0, 0, 0)
    list_view.setIconSize(cached_tile)
    list_view.setGridSize(grid_stride)
    list_view.doItemsLayout()
    list_view.updateGeometries()
    return effective_columns, cached_tile, grid_stride, offset_x, offset_y


def grid_list_height_for_rows(
    row_count: int,
    columns: int,
    grid_stride: QtCore.QSize,
    *,
    top_offset: int = GRID_CONTENT_TOP_OFFSET_PX,
) -> int:
    """Minimum QListView height for row_count cells (no inner vertical scroll)."""
    if row_count <= 0:
        return 1
    cols = max(1, int(columns))
    rows_n = int(math.ceil(row_count / float(cols)))
    return top_offset + rows_n * grid_stride.height()
