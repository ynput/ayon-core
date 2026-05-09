"""Shared Loader selection / drag traversal over ProductsProxyModel (same as list view)."""
from __future__ import annotations

import collections
from typing import List, Optional, Set

from qtpy import QtCore, QtGui

from .products_model import GROUP_TYPE_ROLE, VERSION_ID_ROLE


def collect_version_ids_from_column0_indexes(
    model: QtCore.QAbstractItemModel,
    column0_indexes: List[QtCore.QModelIndex],
) -> Set[str]:
    """Collect version ids from the same rules as `ProductsWidget._get_products_drag_data`."""
    version_ids: Set[str] = set()
    processed_rows = set()
    indexes_queue = collections.deque(column0_indexes)

    while indexes_queue:
        index = indexes_queue.popleft()

        parent_id = (
            index.parent().internalId() if index.parent().isValid() else -1
        )
        index_key = (index.row(), index.column(), parent_id)
        if index_key in processed_rows:
            continue
        processed_rows.add(index_key)

        group_type = model.data(index, GROUP_TYPE_ROLE)

        if group_type == 1:
            row_count = model.rowCount(index)
            for row in range(row_count):
                child_index = model.index(row, 0, index)
                child_version_id = model.data(child_index, VERSION_ID_ROLE)
                if child_version_id is not None:
                    version_ids.add(child_version_id)
        elif group_type == 0:
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                indexes_queue.append(child_index)
        else:
            version_id = model.data(index, VERSION_ID_ROLE)
            if version_id is not None:
                version_ids.add(version_id)

    return version_ids


def find_root_group_column0_index(
    proxy_model: QtCore.QAbstractItemModel,
    group_name: str,
) -> QtCore.QModelIndex:
    """Locate a root-level regular group row (`GROUP_TYPE_ROLE == 0`) by display label."""
    root = QtCore.QModelIndex()
    for row in range(proxy_model.rowCount(root)):
        ix = proxy_model.index(row, 0, root)
        if proxy_model.data(ix, GROUP_TYPE_ROLE) != 0:
            continue
        label = proxy_model.data(ix, QtCore.Qt.DisplayRole)
        if label == group_name:
            return ix
    return QtCore.QModelIndex()
