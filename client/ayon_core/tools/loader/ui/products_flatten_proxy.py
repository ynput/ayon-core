"""Flattening proxy: exposes only product (leaf) rows from the tree as a flat list."""
from __future__ import annotations

import collections
import datetime
from typing import List, Optional

from qtpy import QtCore

from ayon_core.tools.utils.lib import format_version

from .products_model import (
    GROUP_NAME_ROLE,
    GROUP_TYPE_ROLE,
    PRODUCT_ID_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_NAME_ROLE,
    VERSION_STATUS_NAME_ROLE,
    VERSION_PUBLISH_TIME_ROLE,
    VERSION_AUTHOR_ROLE,
)


def regular_group_name_for_product_leaf(
    model: QtCore.QAbstractItemModel,
    source_index: QtCore.QModelIndex,
) -> Optional[str]:
    """Name of the enclosing regular group row (GROUP_TYPE 0), else None (ungrouped)."""
    parent = source_index.parent()
    if not parent.isValid():
        return None
    gt = model.data(parent, GROUP_TYPE_ROLE)
    if gt == 0:
        text = model.data(parent, QtCore.Qt.DisplayRole)
        return str(text) if text else None
    if gt == 1:
        gp = parent.parent()
        if gp.isValid() and model.data(gp, GROUP_TYPE_ROLE) == 0:
            text = model.data(gp, QtCore.Qt.DisplayRole)
            return str(text) if text else None
    return None


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


class ProductsFlattenProxyModel(QtCore.QAbstractProxyModel):
    """Proxy that flattens the products tree to a list of product-only rows for grid view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._source_indexes: List[QtCore.QModelIndex] = []

    def set_controller(self, controller) -> None:
        self._controller = controller

    def setSourceModel(self, source_model: QtCore.QAbstractItemModel) -> None:
        old = self.sourceModel()
        if old:
            old.layoutChanged.disconnect(self._rebuild_mapping)
            old.modelReset.disconnect(self._rebuild_mapping)
            old.rowsInserted.disconnect(self._rebuild_mapping)
            old.rowsRemoved.disconnect(self._rebuild_mapping)
        super().setSourceModel(source_model)
        if source_model:
            source_model.layoutChanged.connect(self._rebuild_mapping)
            source_model.modelReset.connect(self._rebuild_mapping)
            source_model.rowsInserted.connect(self._rebuild_mapping)
            source_model.rowsRemoved.connect(self._rebuild_mapping)
        self._rebuild_mapping()

    def _rebuild_mapping(self) -> None:
        self.beginResetModel()
        source = self.sourceModel()
        self._source_indexes = _collect_product_indexes(source) if source else []
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._source_indexes)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        source = self.sourceModel()
        if not source:
            return 0
        return source.columnCount(QtCore.QModelIndex())

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:
        if parent.isValid() or row < 0 or row >= len(self._source_indexes):
            return QtCore.QModelIndex()
        return self.createIndex(row, column, row)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._source_indexes):
            return None
        source_index = self._source_indexes[row]
        if not source_index.isValid():
            return None
        model = self.sourceModel()
        if role == QtCore.Qt.ToolTipRole:
            return self._build_tooltip(model, source_index)
        if role == GROUP_NAME_ROLE:
            return regular_group_name_for_product_leaf(model, source_index)
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
        if row < 0 or row >= len(self._source_indexes):
            return QtCore.QModelIndex()
        base = self._source_indexes[row]
        if proxy_index.column() == 0:
            return base
        return self.sourceModel().index(base.row(), proxy_index.column(), base.parent())

    def mapFromSource(self, source_index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not source_index.isValid():
            return QtCore.QModelIndex()
        for row, idx in enumerate(self._source_indexes):
            if idx == source_index:
                return self.createIndex(row, source_index.column(), row)
        return QtCore.QModelIndex()


class ProductsGridGroupFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Slice of ProductsFlattenProxyModel: one regular group or ungrouped (group_key None)."""

    def __init__(self, group_key: Optional[str], parent=None):
        super().__init__(parent)
        self._group_key = group_key

    def group_key(self) -> Optional[str]:
        return self._group_key

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QtCore.QModelIndex,
    ) -> bool:
        if source_parent.isValid():
            return False
        src = self.sourceModel()
        if src is None:
            return False
        idx = src.index(source_row, 0, source_parent)
        if not idx.isValid():
            return False
        name = idx.data(GROUP_NAME_ROLE)
        if self._group_key is None:
            return name is None
        return name == self._group_key
