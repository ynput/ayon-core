"""Flattening proxy: exposes product rows (and optional section headers) for grid view."""
from __future__ import annotations

import collections
import datetime
from typing import List, Optional, Sequence, Set, Tuple

from qtpy import QtCore

from ayon_core.tools.utils.lib import format_version

from .products_model import (
    GROUP_TYPE_ROLE,
    PRODUCT_ID_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_NAME_ROLE,
    VERSION_STATUS_NAME_ROLE,
    VERSION_PUBLISH_TIME_ROLE,
    VERSION_AUTHOR_ROLE,
)

# Synthetic grid rows (no backing QStandardItem): section title band.
GRID_ROW_IS_HEADER_ROLE = QtCore.Qt.UserRole + 90
GRID_SECTION_GROUP_KEY_ROLE = QtCore.Qt.UserRole + 91

# Flat row tuples stored internally:
#   ("p", QModelIndex) — product leaf mapped from source proxy
#   ("h", title: str, group_key: str) — section header row (no source index)


def _collect_product_indexes(model: QtCore.QAbstractItemModel) -> List[QtCore.QModelIndex]:
    """Depth-first collect all source indexes that have PRODUCT_ID_ROLE (product rows)."""
    result: List[QtCore.QModelIndex] = []
    stack: collections.deque = collections.deque()
    for row in range(model.rowCount(QtCore.QModelIndex())):
        stack.append(model.index(row, 0, QtCore.QModelIndex()))

    while stack:
        index = stack.popleft()
        if not index.isValid():
            continue
        if model.data(index, PRODUCT_ID_ROLE) is not None:
            result.append(index)
        for row in range(model.rowCount(index)):
            stack.append(model.index(row, 0, index))
    return result


def _collect_under_merged(
    model: QtCore.QAbstractItemModel, merged_parent: QtCore.QModelIndex
) -> List[QtCore.QModelIndex]:
    """Product leaves under a merged-name folder (recursive for nested merges)."""
    out: List[QtCore.QModelIndex] = []
    for row in range(model.rowCount(merged_parent)):
        idx = model.index(row, 0, merged_parent)
        if model.data(idx, PRODUCT_ID_ROLE) is not None:
            out.append(idx)
        elif model.data(idx, GROUP_TYPE_ROLE) == 1:
            out.extend(_collect_under_merged(model, idx))
    return out


def _collect_under_group_folder(
    model: QtCore.QAbstractItemModel, group_idx: QtCore.QModelIndex
) -> List[QtCore.QModelIndex]:
    """All product rows inside a productGroup folder (incl. merged-name buckets)."""
    out: List[QtCore.QModelIndex] = []
    for row in range(model.rowCount(group_idx)):
        idx = model.index(row, 0, group_idx)
        if model.data(idx, PRODUCT_ID_ROLE) is not None:
            out.append(idx)
        elif model.data(idx, GROUP_TYPE_ROLE) == 1:
            out.extend(_collect_under_merged(model, idx))
    return out


def enumerate_grid_section_source_indexes(
    proxy: QtCore.QAbstractItemModel,
) -> List[Tuple[Optional[str], List[QtCore.QModelIndex]]]:
    """Split the products tree into grid sections matching list-view visual order.

    Each tuple is ``(header_title, flat_product_indexes)``. ``header_title`` is
    ``None`` for a headerless bucket (root-level products / merged buckets not
    under a named group). ``header_title`` is the group row label when the
    section is a ``productGroup`` folder (``GROUP_TYPE_ROLE == 0``).

    Args:
        proxy: Typically :class:`ProductsProxyModel` (same source as list/grid).

    Returns:
        Ordered sections; each second element lists proxy-level indexes for cards.

    """
    root = QtCore.QModelIndex()
    sections: List[Tuple[Optional[str], List[QtCore.QModelIndex]]] = []
    batch: List[QtCore.QModelIndex] = []

    def flush_batch() -> None:
        nonlocal batch
        if batch:
            sections.append((None, batch))
            batch = []

    n = proxy.rowCount(root)
    for row in range(n):
        idx = proxy.index(row, 0, root)
        gt = proxy.data(idx, GROUP_TYPE_ROLE)
        if gt == 0:
            flush_batch()
            title = str(proxy.data(idx, QtCore.Qt.DisplayRole) or "")
            sections.append(
                (title, _collect_under_group_folder(proxy, idx))
            )
            continue
        if proxy.data(idx, PRODUCT_ID_ROLE) is not None:
            batch.append(idx)
        elif gt == 1:
            batch.extend(_collect_under_merged(proxy, idx))
        else:
            continue
    flush_batch()
    return sections


def build_unified_grid_flat_rows(
    proxy: QtCore.QAbstractItemModel,
    *,
    collapsed_group_keys: Optional[Set[str]] = None,
) -> List[Tuple]:
    """Single ordered flat row list: optional header band then product rows per section.

    Mirrors list-view grouping order. For a **collapsed** named group, the header
    row is still emitted so the user can expand again; product rows under that
    group are omitted.

    Row tuples:
        ``("h", title, group_key)`` — section header (named groups only)
        ``("p", QModelIndex)`` — product row

    ``group_key`` matches :meth:`ProductsGridWidget._section_storage_key`.
    """
    collapsed_group_keys = collapsed_group_keys or set()
    specs = enumerate_grid_section_source_indexes(proxy)
    out: List[Tuple] = []
    for title, indexes in specs:
        if title is None:
            if not indexes:
                continue
            for idx in indexes:
                out.append(("p", idx))
            continue
        if not indexes:
            continue
        key = str(title)
        out.append(("h", key, key))
        if key in collapsed_group_keys:
            continue
        for idx in indexes:
            out.append(("p", idx))
    return out


class ProductsFlattenProxyModel(QtCore.QAbstractProxyModel):
    """Proxy that flattens the products tree for grid view.

    Rows are either product leaves mapped from the source proxy, or synthetic
    section-header rows (see ``build_unified_grid_flat_rows``).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._flat_rows: List[Tuple] = []
        self._explicit_flat_rows: Optional[List[Tuple]] = None
        self._explicit_source_indexes: Optional[List[QtCore.QModelIndex]] = None
        self._auto_rebuild_from_source = True

    def set_controller(self, controller) -> None:
        self._controller = controller

    def set_auto_rebuild_from_source(self, enabled: bool) -> None:
        """When False, source layout signals do not rebuild (grid-driven layout)."""
        self._auto_rebuild_from_source = bool(enabled)

    def set_explicit_flat_rows(self, rows: Optional[Sequence[Tuple]]) -> None:
        """Use a fixed ordered row list (headers + product indexes).

        Pass ``None`` to clear explicit layout and fall back to scanning the tree.
        """
        self._explicit_flat_rows = list(rows) if rows is not None else None
        if self._explicit_flat_rows is not None:
            self._explicit_source_indexes = None
        self._apply_flat_mapping()

    def set_explicit_source_indexes(
        self, indexes: Optional[Sequence[QtCore.QModelIndex]]
    ) -> None:
        """Use a fixed ordered product-index list (no section headers)."""
        self._explicit_source_indexes = (
            list(indexes) if indexes is not None else None
        )
        if self._explicit_source_indexes is not None:
            self._explicit_flat_rows = None
        self._apply_flat_mapping()

    def setSourceModel(self, source_model: QtCore.QAbstractItemModel) -> None:
        old = self.sourceModel()
        if old:
            self._disconnect_source_signals(old)
        super().setSourceModel(source_model)
        if source_model:
            self._connect_source_signals(source_model)
        self._apply_flat_mapping()

    def _connect_source_signals(self, source_model: QtCore.QAbstractItemModel) -> None:
        source_model.layoutChanged.connect(self._on_source_structure_changed)
        source_model.modelReset.connect(self._on_source_structure_changed)
        source_model.rowsInserted.connect(self._on_source_structure_changed)
        source_model.rowsRemoved.connect(self._on_source_structure_changed)

    def _disconnect_source_signals(self, source_model: QtCore.QAbstractItemModel) -> None:
        source_model.layoutChanged.disconnect(self._on_source_structure_changed)
        source_model.modelReset.disconnect(self._on_source_structure_changed)
        source_model.rowsInserted.disconnect(self._on_source_structure_changed)
        source_model.rowsRemoved.disconnect(self._on_source_structure_changed)

    def _on_source_structure_changed(self) -> None:
        if not self._auto_rebuild_from_source:
            return
        self._apply_flat_mapping()

    def _apply_flat_mapping(self) -> None:
        self.beginResetModel()
        source = self.sourceModel()
        if not source:
            self._flat_rows = []
        elif self._explicit_flat_rows is not None:
            self._flat_rows = list(self._explicit_flat_rows)
        elif self._explicit_source_indexes is not None:
            self._flat_rows = [
                ("p", idx) for idx in self._explicit_source_indexes
            ]
        else:
            self._flat_rows = [
                ("p", idx) for idx in _collect_product_indexes(source)
            ]
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._flat_rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        source = self.sourceModel()
        if not source:
            return 0
        return source.columnCount(QtCore.QModelIndex())

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:
        if parent.isValid() or row < 0 or row >= len(self._flat_rows):
            return QtCore.QModelIndex()
        return self.createIndex(row, column, row)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        row = index.row()
        if row < 0 or row >= len(self._flat_rows):
            return QtCore.Qt.ItemFlag.NoItemFlags
        spec = self._flat_rows[row]
        if spec[0] == "h":
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        src = self.mapToSource(index)
        if not src.isValid():
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        return self.sourceModel().flags(src)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._flat_rows):
            return None
        spec = self._flat_rows[row]
        if spec[0] == "h":
            title = spec[1]
            group_key = spec[2]
            if role == QtCore.Qt.DisplayRole:
                return title
            if role == GRID_ROW_IS_HEADER_ROLE:
                return True
            if role == GRID_SECTION_GROUP_KEY_ROLE:
                return group_key
            return None
        source_index = spec[1]
        if not source_index.isValid():
            return None
        model = self.sourceModel()
        if role == GRID_ROW_IS_HEADER_ROLE:
            return False
        if role == GRID_SECTION_GROUP_KEY_ROLE:
            return None
        if role == QtCore.Qt.ToolTipRole:
            return self._build_tooltip(model, source_index)
        return model.data(source_index, role)

    def _build_tooltip(self, model: QtCore.QAbstractItemModel, source_index: QtCore.QModelIndex) -> str:
        product_name = model.data(source_index, PRODUCT_NAME_ROLE) or "—"
        version = model.data(source_index, VERSION_NAME_ROLE)
        pn = (
            model.get_last_project_name()
            if hasattr(model, "get_last_project_name")
            else None
        )
        vp = (
            self._controller.get_version_padding(pn)
            if self._controller is not None
            else 3
        )
        version_label = (
            format_version(version, version_padding=vp)
            if version is not None
            else "—"
        )
        status = model.data(source_index, VERSION_STATUS_NAME_ROLE) or "—"
        published = model.data(source_index, VERSION_PUBLISH_TIME_ROLE)
        if published:
            try:
                created = datetime.datetime.strptime(published, "%Y%m%dT%H%M%SZ")
                published = created.strftime("%b %d %Y %H:%M")
            except (ValueError, TypeError):
                pass
        else:
            published = "—"
        author = model.data(source_index, VERSION_AUTHOR_ROLE) or "—"
        return (
            f"<b>{product_name}</b><br>"
            f"Version: {version_label}<br>"
            f"Status: {status}<br>"
            f"Created: {published}<br>"
            f"Author: {author}"
        )

    def mapToSource(self, proxy_index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not proxy_index.isValid():
            return QtCore.QModelIndex()
        row = proxy_index.row()
        if row < 0 or row >= len(self._flat_rows):
            return QtCore.QModelIndex()
        spec = self._flat_rows[row]
        if spec[0] != "p":
            return QtCore.QModelIndex()
        base = spec[1]
        if proxy_index.column() == 0:
            return base
        return self.sourceModel().index(base.row(), proxy_index.column(), base.parent())

    def mapFromSource(self, source_index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not source_index.isValid():
            return QtCore.QModelIndex()
        for row, spec in enumerate(self._flat_rows):
            if spec[0] == "p" and spec[1] == source_index:
                return self.createIndex(row, source_index.column(), row)
        return QtCore.QModelIndex()
