import uuid
from qtpy import QtGui, QtCore

from ayon_core.pipeline import discover_legacy_creator_plugins

from . constants import (
    PRODUCT_TYPE_ROLE,
    ITEM_ID_ROLE
)


class CreatorsModel(QtGui.QStandardItemModel):
    def __init__(self, *args, **kwargs):
        super(CreatorsModel, self).__init__(*args, **kwargs)

        self._creators_by_id = {}

    def reset(self):
        # TODO change to refresh when clearing is not needed
        self.clear()
        self._creators_by_id = {}

        items = []
        creators = discover_legacy_creator_plugins()
        for creator in creators:
            if not creator.enabled:
                continue
            item_id = str(uuid.uuid4())
            self._creators_by_id[item_id] = creator

            label = creator.label or creator.product_type
            item = QtGui.QStandardItem(label)
            item.setEditable(False)
            item.setData(item_id, ITEM_ID_ROLE)
            item.setData(creator.product_type, PRODUCT_TYPE_ROLE)
            items.append(item)

        if not items:
            item = QtGui.QStandardItem("No registered create plugins")
            item.setEnabled(False)
            item.setData(False, QtCore.Qt.ItemIsEnabled)
            items.append(item)

        items.sort(key=lambda item: item.text())
        self.invisibleRootItem().appendRows(items)

    def get_creator_by_id(self, item_id):
        return self._creators_by_id.get(item_id)

    def get_indexes_by_product_type(self, product_type):
        indexes = []
        for row in range(self.rowCount()):
            index = self.index(row, 0)
            item_id = index.data(ITEM_ID_ROLE)
            creator_plugin = self._creators_by_id.get(item_id)
            if creator_plugin and (
                creator_plugin.label.lower() == product_type.lower()
                or creator_plugin.product_type.lower() == product_type.lower()
            ):
                indexes.append(index)
        return indexes
