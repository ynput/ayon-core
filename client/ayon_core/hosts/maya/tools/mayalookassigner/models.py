from collections import defaultdict

from qtpy import QtCore
import qtawesome

from ayon_core.tools.utils import models
from ayon_core.style import get_default_entity_icon_color


class AssetModel(models.TreeModel):

    Columns = ["label"]

    def __init__(self, *args, **kwargs):
        super(AssetModel, self).__init__(*args, **kwargs)

        self._icon_color = get_default_entity_icon_color()

    def add_items(self, items):
        """
        Add items to model with needed data
        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Add the items sorted by label
        def sorter(x):
            return x["label"]

        for item in sorted(items, key=sorter):

            asset_item = models.Item()
            asset_item.update(item)
            asset_item["icon"] = "folder"

            # Add namespace children
            namespaces = item["namespaces"]
            for namespace in sorted(namespaces):
                child = models.Item()
                child.update(item)
                child.update({
                    "label": (namespace if namespace != ":"
                              else "(no namespace)"),
                    "namespace": namespace,
                    "looks": item["looks"],
                    "icon": "folder-o"
                })
                asset_item.add_child(child)

            self.add_child(asset_item)

        self.endResetModel()

    def data(self, index, role):

        if not index.isValid():
            return

        if role == models.TreeModel.ItemRole:
            node = index.internalPointer()
            return node

        # Add icon
        if role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                node = index.internalPointer()
                icon = node.get("icon")
                if icon:
                    return qtawesome.icon(
                        "fa.{0}".format(icon),
                        color=self._icon_color
                    )

        return super(AssetModel, self).data(index, role)


class LookModel(models.TreeModel):
    """Model displaying a list of looks and matches for assets"""

    Columns = ["label", "match"]

    def add_items(self, items):
        """Add items to model with needed data

        An item exists of:
            {
                "product": 'name of product',
                "asset": asset_document
            }

        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Collect the assets per look name (from the items of the AssetModel)
        look_products = defaultdict(list)
        for asset_item in items:
            folder_entity = asset_item["folder_entity"]
            for look in asset_item["looks"]:
                look_products[look["name"]].append(folder_entity)

        for product_name in sorted(look_products.keys()):
            folder_entities = look_products[product_name]

            # Define nice label without "look" prefix for readability
            label = (
                product_name
                if not product_name.startswith("look")
                else product_name[4:]
            )

            item_node = models.Item()
            item_node["label"] = label
            item_node["product"] = product_name

            # Amount of matching assets for this look
            item_node["match"] = len(folder_entities)

            # Store the assets that have this product available
            item_node["folder_entities"] = folder_entities

            self.add_child(item_node)

        self.endResetModel()
