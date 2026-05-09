"""Maps one root-level tree row from ProductsProxyModel into a QAbstractProxyModel.

One row only — expand/collapse for grid sections is driven by a header chevron button,
not QTreeView branches (avoids hidden-child vs branch-indicator quirks).
"""
from __future__ import annotations

from qtpy import QtCore

_GRP = object()


class SingleGroupRowProxyModel(QtCore.QAbstractProxyModel):
    """Maps a single root group row for the mini ProductView strip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mapped_col0: QtCore.QModelIndex = QtCore.QModelIndex()

    def set_mapped_group_column0_index(self, proxy_column0_index: QtCore.QModelIndex) -> None:
        """Root-level column-0 index on the source (ProductsProxyModel)."""
        self.beginResetModel()
        self._mapped_col0 = QtCore.QModelIndex(proxy_column0_index)
        self.endResetModel()

    def clear_mapping(self) -> None:
        self.beginResetModel()
        self._mapped_col0 = QtCore.QModelIndex()
        self.endResetModel()

    def mapped_column0_index(self) -> QtCore.QModelIndex:
        return QtCore.QModelIndex(self._mapped_col0)

    def _src_col_count(self) -> int:
        src = self.sourceModel()
        return src.columnCount(QtCore.QModelIndex()) if src else 0

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if not self._mapped_col0.isValid():
            return 0
        return 1 if not parent.isValid() else 0

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return self._src_col_count()

    def index(
        self,
        row: int,
        column: int,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),
    ) -> QtCore.QModelIndex:
        cc = self._src_col_count()
        if column < 0 or column >= cc:
            return QtCore.QModelIndex()
        src = self.sourceModel()
        if src is None or not self._mapped_col0.isValid():
            return QtCore.QModelIndex()
        if not parent.isValid() and row == 0:
            return self.createIndex(0, column, _GRP)
        return QtCore.QModelIndex()

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def mapToSource(self, proxy_index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not proxy_index.isValid() or not self._mapped_col0.isValid():
            return QtCore.QModelIndex()
        src = self.sourceModel()
        if src is None or proxy_index.internalPointer() is not _GRP:
            return QtCore.QModelIndex()
        return src.index(
            self._mapped_col0.row(),
            proxy_index.column(),
            self._mapped_col0.parent(),
        )

    def mapFromSource(self, source_index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not self._mapped_col0.isValid():
            return QtCore.QModelIndex()
        if (
            source_index.parent() == self._mapped_col0.parent()
            and source_index.row() == self._mapped_col0.row()
        ):
            return self.index(0, source_index.column(), QtCore.QModelIndex())
        return QtCore.QModelIndex()

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ):
        src = self.sourceModel()
        if src is None or orientation != QtCore.Qt.Horizontal:
            return None
        return src.headerData(section, orientation, role)
