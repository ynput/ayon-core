import collections

import qtawesome
from qtpy import QtGui, QtCore

from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon

PRODUCTS_MODEL_SENDER_NAME = "qt_products_model"

GROUP_TYPE_ROLE = QtCore.Qt.UserRole + 1
MERGED_COLOR_ROLE = QtCore.Qt.UserRole + 2
FOLDER_LABEL_ROLE = QtCore.Qt.UserRole + 3
FOLDER_ID_ROLE = QtCore.Qt.UserRole + 4
PRODUCT_ID_ROLE = QtCore.Qt.UserRole + 5
PRODUCT_NAME_ROLE = QtCore.Qt.UserRole + 6
PRODUCT_TYPE_ROLE = QtCore.Qt.UserRole + 7
PRODUCT_TYPE_ICON_ROLE = QtCore.Qt.UserRole + 8
PRODUCT_IN_SCENE_ROLE = QtCore.Qt.UserRole + 9
VERSION_ID_ROLE = QtCore.Qt.UserRole + 10
VERSION_HERO_ROLE = QtCore.Qt.UserRole + 11
VERSION_NAME_ROLE = QtCore.Qt.UserRole + 12
VERSION_NAME_EDIT_ROLE = QtCore.Qt.UserRole + 13
VERSION_PUBLISH_TIME_ROLE = QtCore.Qt.UserRole + 14
VERSION_STATUS_NAME_ROLE = QtCore.Qt.UserRole + 15
VERSION_STATUS_SHORT_ROLE = QtCore.Qt.UserRole + 16
VERSION_STATUS_COLOR_ROLE = QtCore.Qt.UserRole + 17
VERSION_STATUS_ICON_ROLE = QtCore.Qt.UserRole + 18
VERSION_AUTHOR_ROLE = QtCore.Qt.UserRole + 19
VERSION_FRAME_RANGE_ROLE = QtCore.Qt.UserRole + 20
VERSION_DURATION_ROLE = QtCore.Qt.UserRole + 21
VERSION_HANDLES_ROLE = QtCore.Qt.UserRole + 22
VERSION_STEP_ROLE = QtCore.Qt.UserRole + 23
VERSION_AVAILABLE_ROLE = QtCore.Qt.UserRole + 24
VERSION_THUMBNAIL_ID_ROLE = QtCore.Qt.UserRole + 25
ACTIVE_SITE_ICON_ROLE = QtCore.Qt.UserRole + 26
REMOTE_SITE_ICON_ROLE = QtCore.Qt.UserRole + 27
REPRESENTATIONS_COUNT_ROLE = QtCore.Qt.UserRole + 28
SYNC_ACTIVE_SITE_AVAILABILITY = QtCore.Qt.UserRole + 29
SYNC_REMOTE_SITE_AVAILABILITY = QtCore.Qt.UserRole + 30

STATUS_NAME_FILTER_ROLE = QtCore.Qt.UserRole + 31


class ProductsModel(QtGui.QStandardItemModel):
    refreshed = QtCore.Signal()
    version_changed = QtCore.Signal()
    column_labels = [
        "Product name",
        "Product type",
        "Folder",
        "Version",
        "Status",
        "Time",
        "Author",
        "Frames",
        "Duration",
        "Handles",
        "Step",
        "In scene",
        "Availability",
    ]
    merged_items_colors = [
        ("#{0:02x}{1:02x}{2:02x}".format(*c), QtGui.QColor(*c))
        for c in [
            (55, 161, 222),   # Light Blue
            (231, 176, 0),    # Yellow
            (154, 13, 255),   # Purple
            (130, 184, 30),   # Light Green
            (211, 79, 63),    # Light Red
            (179, 181, 182),  # Grey
            (194, 57, 179),   # Pink
            (0, 120, 215),    # Dark Blue
            (0, 204, 106),    # Dark Green
            (247, 99, 12),    # Orange
        ]
    ]

    product_name_col = column_labels.index("Product name")
    product_type_col = column_labels.index("Product type")
    folders_label_col = column_labels.index("Folder")
    version_col = column_labels.index("Version")
    status_col = column_labels.index("Status")
    published_time_col = column_labels.index("Time")
    author_col = column_labels.index("Author")
    frame_range_col = column_labels.index("Frames")
    duration_col = column_labels.index("Duration")
    handles_col = column_labels.index("Handles")
    step_col = column_labels.index("Step")
    in_scene_col = column_labels.index("In scene")
    sitesync_avail_col = column_labels.index("Availability")
    _display_role_mapping = {
        product_name_col: QtCore.Qt.DisplayRole,
        product_type_col: PRODUCT_TYPE_ROLE,
        folders_label_col: FOLDER_LABEL_ROLE,
        version_col: VERSION_NAME_ROLE,
        status_col: VERSION_STATUS_NAME_ROLE,
        published_time_col: VERSION_PUBLISH_TIME_ROLE,
        author_col: VERSION_AUTHOR_ROLE,
        frame_range_col: VERSION_FRAME_RANGE_ROLE,
        duration_col: VERSION_DURATION_ROLE,
        handles_col: VERSION_HANDLES_ROLE,
        step_col: VERSION_STEP_ROLE,
        in_scene_col: PRODUCT_IN_SCENE_ROLE,
        sitesync_avail_col: VERSION_AVAILABLE_ROLE,

    }

    def __init__(self, controller):
        super().__init__()
        self.setColumnCount(len(self.column_labels))
        for idx, label in enumerate(self.column_labels):
            self.setHeaderData(idx, QtCore.Qt.Horizontal, label)
        self._controller = controller

        # Variables to store 'QStandardItem'
        self._items_by_id = {}
        self._group_items_by_name = {}
        self._merged_items_by_id = {}

        # product item objects (they have version information)
        self._product_items_by_id = {}
        self._grouping_enabled = True
        self._reset_merge_color = False
        self._color_iterator = self._color_iter()
        self._group_icon = None

        self._last_project_name = None
        self._last_folder_ids = []
        self._last_project_statuses = {}
        self._last_status_icons_by_name = {}

    def get_product_item_indexes(self):
        return [
            self.indexFromItem(item)
            for item in self._items_by_id.values()
        ]

    def get_product_item_by_id(self, product_id):
        """

        Args:
            product_id (str): Product id.

        Returns:
            Union[ProductItem, None]: Product item with version information.
        """

        return self._product_items_by_id.get(product_id)

    def set_product_version(self, product_id, version_id):
        if version_id is None:
            return

        product_item = self._items_by_id.get(product_id)
        if product_item is None:
            return

        index = self.indexFromItem(product_item)
        self.setData(index, version_id, VERSION_NAME_EDIT_ROLE)

    def set_enable_grouping(self, enable_grouping):
        if enable_grouping is self._grouping_enabled:
            return
        self._grouping_enabled = enable_grouping
        # Ignore change if groups are not available
        self.refresh(
            self._last_project_name,
            self._last_folder_ids
        )

    def flags(self, index):
        # Make the version column editable
        if index.column() == self.version_col and index.data(PRODUCT_ID_ROLE):
            return (
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsEditable
            )
        if index.column() != 0:
            index = self.index(index.row(), 0, index.parent())
        return super().flags(index)

    def data(self, index, role=None):
        if role is None:
            role = QtCore.Qt.DisplayRole

        if not index.isValid():
            return None

        if role in (VERSION_STATUS_SHORT_ROLE, VERSION_STATUS_COLOR_ROLE):
            status_name = self.data(index, VERSION_STATUS_NAME_ROLE)
            status_item = self._last_project_statuses.get(status_name)
            if status_item is None:
                return ""
            if role == VERSION_STATUS_SHORT_ROLE:
                return status_item.short
            return status_item.color

        col = index.column()
        if col == self.status_col and role == QtCore.Qt.DecorationRole:
            role = VERSION_STATUS_ICON_ROLE

        if role == VERSION_STATUS_ICON_ROLE:
            status_name = self.data(index, VERSION_STATUS_NAME_ROLE)
            return self._get_status_icon(status_name)

        if col == 0:
            return super().data(index, role)

        if role == QtCore.Qt.DecorationRole:
            if col == 1:
                role = PRODUCT_TYPE_ICON_ROLE
            else:
                return None

        if (
            role == VERSION_NAME_EDIT_ROLE
            or (role == QtCore.Qt.EditRole and col == self.version_col)
        ):
            index = self.index(index.row(), 0, index.parent())
            product_id = index.data(PRODUCT_ID_ROLE)
            product_item = self._product_items_by_id.get(product_id)
            if product_item is None:
                return None
            product_items = list(product_item.version_items.values())
            product_items.sort(reverse=True)
            return product_items

        if role == QtCore.Qt.EditRole:
            return None

        if role == QtCore.Qt.DisplayRole:
            if not index.data(PRODUCT_ID_ROLE):
                return None
            role = self._display_role_mapping.get(col)
            if role is None:
                return None

        index = self.index(index.row(), 0, index.parent())

        return super().data(index, role)

    def setData(self, index, value, role=None):
        if not index.isValid():
            return False

        if role is None:
            role = QtCore.Qt.EditRole

        col = index.column()
        if col == self.version_col and role == QtCore.Qt.EditRole:
            role = VERSION_NAME_EDIT_ROLE

        if role == VERSION_NAME_EDIT_ROLE:
            if col != 0:
                index = self.index(index.row(), 0, index.parent())
            product_id = index.data(PRODUCT_ID_ROLE)
            product_item = self._product_items_by_id[product_id]
            final_version_item = None
            for v_id, version_item in product_item.version_items.items():
                if v_id == value:
                    final_version_item = version_item
                    break

            if final_version_item is None:
                return False
            if index.data(VERSION_ID_ROLE) == final_version_item.version_id:
                return True
            item = self.itemFromIndex(index)
            self._set_version_data_to_product_item(item, final_version_item)
            self.version_changed.emit()
            return True
        return super().setData(index, value, role)

    def _get_next_color(self):
        return next(self._color_iterator)

    def _color_iter(self):
        while True:
            for color in self.merged_items_colors:
                if self._reset_merge_color:
                    self._reset_merge_color = False
                    break
                yield color

    def _get_status_icon(self, status_name):
        icon = self._last_status_icons_by_name.get(status_name)
        if icon is not None:
            return icon

        status_item = self._last_project_statuses.get(status_name)
        if status_item is not None:
            icon = get_qt_icon({
                "type": "material-symbols",
                "name": status_item.icon,
                "color": status_item.color,
            })

        if icon is None:
            icon = QtGui.QIcon()

        self._last_status_icons_by_name[status_name] = icon
        return icon

    def _clear(self):
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        self._items_by_id = {}
        self._group_items_by_name = {}
        self._merged_items_by_id = {}
        self._product_items_by_id = {}
        self._reset_merge_color = True

    def _get_group_icon(self):
        if self._group_icon is None:
            self._group_icon = qtawesome.icon(
                "fa.object-group",
                color=get_default_entity_icon_color()
            )
        return self._group_icon

    def _get_group_model_item(self, group_name):
        model_item = self._group_items_by_name.get(group_name)
        if model_item is None:
            model_item = QtGui.QStandardItem(group_name)
            model_item.setData(
                self._get_group_icon(), QtCore.Qt.DecorationRole
            )
            model_item.setData(0, GROUP_TYPE_ROLE)
            model_item.setEditable(False)
            model_item.setColumnCount(self.columnCount())
            self._group_items_by_name[group_name] = model_item
        return model_item

    def _get_merged_model_item(self, path, count, hex_color):
        model_item = self._merged_items_by_id.get(path)
        if model_item is None:
            model_item = QtGui.QStandardItem()
            model_item.setData(1, GROUP_TYPE_ROLE)
            model_item.setData(hex_color, MERGED_COLOR_ROLE)
            model_item.setEditable(False)
            model_item.setColumnCount(self.columnCount())
            self._merged_items_by_id[path] = model_item
        label = "{} ({})".format(path, count)
        model_item.setData(label, QtCore.Qt.DisplayRole)
        return model_item

    def _set_version_data_to_product_item(
        self,
        model_item,
        version_item,
        repre_count_by_version_id=None,
        sync_availability_by_version_id=None,
    ):
        """

        Args:
            model_item (QtGui.QStandardItem): Item which should have values
                from version item.
            version_item (VersionItem): Item from entities model with
                information about version.
            repre_count_by_version_id (Optional[str, int]): Mapping of
                representation count by version id.
            sync_availability_by_version_id (Optional[str, Tuple[int, int]]):
                Mapping of sync availability by version id.

        """
        model_item.setData(version_item.version_id, VERSION_ID_ROLE)
        model_item.setData(version_item.version, VERSION_NAME_ROLE)
        model_item.setData(version_item.is_hero, VERSION_HERO_ROLE)
        model_item.setData(
            version_item.published_time, VERSION_PUBLISH_TIME_ROLE
        )
        model_item.setData(version_item.author, VERSION_AUTHOR_ROLE)
        model_item.setData(version_item.status, VERSION_STATUS_NAME_ROLE)
        model_item.setData(version_item.frame_range, VERSION_FRAME_RANGE_ROLE)
        model_item.setData(version_item.duration, VERSION_DURATION_ROLE)
        model_item.setData(version_item.handles, VERSION_HANDLES_ROLE)
        model_item.setData(version_item.step, VERSION_STEP_ROLE)
        model_item.setData(
            version_item.thumbnail_id, VERSION_THUMBNAIL_ID_ROLE)

        # TODO call site sync methods for all versions at once
        project_name = self._last_project_name
        version_id = version_item.version_id
        if repre_count_by_version_id is None:
            repre_count_by_version_id = (
                self._controller.get_versions_representation_count(
                    project_name, [version_id]
                )
            )
        if sync_availability_by_version_id is None:
            sync_availability_by_version_id = (
                self._controller.get_version_sync_availability(
                    project_name, [version_id]
                )
            )
        repre_count = repre_count_by_version_id[version_id]
        active, remote = sync_availability_by_version_id[version_id]

        model_item.setData(repre_count, REPRESENTATIONS_COUNT_ROLE)
        model_item.setData(active, SYNC_ACTIVE_SITE_AVAILABILITY)
        model_item.setData(remote, SYNC_REMOTE_SITE_AVAILABILITY)

    def _get_product_model_item(
        self,
        product_item,
        active_site_icon,
        remote_site_icon,
        repre_count_by_version_id,
        sync_availability_by_version_id,
        last_version_by_product_id,
    ):
        model_item = self._items_by_id.get(product_item.product_id)
        last_version = last_version_by_product_id[product_item.product_id]

        statuses = {
            version_item.status
            for version_item in product_item.version_items.values()
        }
        if model_item is None:
            product_id = product_item.product_id
            model_item = QtGui.QStandardItem(product_item.product_name)
            model_item.setEditable(False)
            icon = get_qt_icon(product_item.product_icon)
            product_type_icon = get_qt_icon(product_item.product_type_icon)
            model_item.setColumnCount(self.columnCount())
            model_item.setData(icon, QtCore.Qt.DecorationRole)
            model_item.setData(product_id, PRODUCT_ID_ROLE)
            model_item.setData(product_item.product_name, PRODUCT_NAME_ROLE)
            model_item.setData(product_item.product_type, PRODUCT_TYPE_ROLE)
            model_item.setData(product_type_icon, PRODUCT_TYPE_ICON_ROLE)
            model_item.setData(product_item.folder_id, FOLDER_ID_ROLE)

            self._product_items_by_id[product_id] = product_item
            self._items_by_id[product_id] = model_item

        model_item.setData("|".join(statuses), STATUS_NAME_FILTER_ROLE)
        model_item.setData(product_item.folder_label, FOLDER_LABEL_ROLE)
        in_scene = 1 if product_item.product_in_scene else 0
        model_item.setData(in_scene, PRODUCT_IN_SCENE_ROLE)

        model_item.setData(active_site_icon, ACTIVE_SITE_ICON_ROLE)
        model_item.setData(remote_site_icon, REMOTE_SITE_ICON_ROLE)

        self._set_version_data_to_product_item(
            model_item,
            last_version,
            repre_count_by_version_id,
            sync_availability_by_version_id,
        )
        return model_item

    def get_last_project_name(self):
        return self._last_project_name

    def refresh(self, project_name, folder_ids):
        self._clear()

        self._last_project_name = project_name
        self._last_folder_ids = folder_ids
        status_items = self._controller.get_project_status_items(project_name)
        self._last_project_statuses = {
            status_item.name: status_item
            for status_item in status_items
        }
        self._last_status_icons_by_name = {}

        active_site_icon_def = self._controller.get_active_site_icon_def(
            project_name
        )
        remote_site_icon_def = self._controller.get_remote_site_icon_def(
            project_name
        )
        active_site_icon = get_qt_icon(active_site_icon_def)
        remote_site_icon = get_qt_icon(remote_site_icon_def)

        product_items = self._controller.get_product_items(
            project_name,
            folder_ids,
            sender=PRODUCTS_MODEL_SENDER_NAME
        )
        product_items_by_id = {
            product_item.product_id: product_item
            for product_item in product_items
        }
        last_version_by_product_id = {}
        for product_item in product_items:
            versions = list(product_item.version_items.values())
            versions.sort()
            last_version = versions[-1]
            last_version_by_product_id[product_item.product_id] = (
                last_version
            )

        version_ids = {
            version_item.version_id
            for version_item in last_version_by_product_id.values()
        }
        repre_count_by_version_id = (
            self._controller.get_versions_representation_count(
                project_name, version_ids
            )
        )
        sync_availability_by_version_id = (
            self._controller.get_version_sync_availability(
                project_name, version_ids
            )
        )

        # Prepare product groups
        product_name_matches_by_group = collections.defaultdict(dict)
        for product_item in product_items_by_id.values():
            group_name = None
            if self._grouping_enabled:
                group_name = product_item.group_name

            product_name = product_item.product_name
            group = product_name_matches_by_group[group_name]
            group.setdefault(product_name, []).append(product_item)

        group_names = set(product_name_matches_by_group.keys())

        root_item = self.invisibleRootItem()
        new_root_items = []
        merged_paths = set()
        for group_name in group_names:
            key_parts = []
            if group_name:
                key_parts.append(group_name)

            groups = product_name_matches_by_group[group_name]
            merged_product_items = {}
            top_items = []
            group_product_types = set()
            group_status_names = set()
            for product_name, product_items in groups.items():
                group_product_types |= {p.product_type for p in product_items}
                for product_item in product_items:
                    group_status_names |= {
                        version_item.status
                        for version_item in product_item.version_items.values()
                    }
                    group_product_types.add(product_item.product_type)

                if len(product_items) == 1:
                    top_items.append(product_items[0])
                else:
                    path = "/".join(key_parts + [product_name])
                    merged_paths.add(path)
                    merged_product_items[path] = (
                        product_name,
                        product_items,
                    )

            parent_item = None
            if group_name:
                parent_item = self._get_group_model_item(group_name)
                parent_item.setData(
                    "|".join(group_product_types),
                    PRODUCT_TYPE_ROLE
                )
                parent_item.setData(
                    "|".join(group_status_names),
                    STATUS_NAME_FILTER_ROLE
                )

            new_items = []
            if parent_item is not None and parent_item.row() < 0:
                new_root_items.append(parent_item)

            for product_item in top_items:
                item = self._get_product_model_item(
                    product_item,
                    active_site_icon,
                    remote_site_icon,
                    repre_count_by_version_id,
                    sync_availability_by_version_id,
                    last_version_by_product_id,
                )
                new_items.append(item)

            for path_info in merged_product_items.values():
                product_name, product_items = path_info
                (merged_color_hex, merged_color_qt) = self._get_next_color()
                merged_color = qtawesome.icon(
                    "fa.circle", color=merged_color_qt
                )
                merged_item = self._get_merged_model_item(
                    product_name, len(product_items), merged_color_hex)
                merged_item.setData(merged_color, QtCore.Qt.DecorationRole)
                new_items.append(merged_item)

                merged_product_types = set()
                merged_status_names = set()
                new_merged_items = []
                for product_item in product_items:
                    item = self._get_product_model_item(
                        product_item,
                        active_site_icon,
                        remote_site_icon,
                        repre_count_by_version_id,
                        sync_availability_by_version_id,
                        last_version_by_product_id,
                    )
                    new_merged_items.append(item)
                    merged_product_types.add(product_item.product_type)
                    merged_status_names |= {
                        version_item.status
                        for version_item in (
                            product_item.version_items.values()
                        )
                    }

                merged_item.setData(
                    "|".join(merged_product_types),
                    PRODUCT_TYPE_ROLE
                )
                merged_item.setData(
                    "|".join(merged_status_names),
                    STATUS_NAME_FILTER_ROLE
                )
                if new_merged_items:
                    merged_item.appendRows(new_merged_items)

            if not new_items:
                continue

            if parent_item is None:
                new_root_items.extend(new_items)
            else:
                parent_item.appendRows(new_items)

        if new_root_items:
            root_item.appendRows(new_root_items)

        self.refreshed.emit()
    # ---------------------------------
    #   This implementation does not call '_clear' at the start
    #       but is more complex and probably slower
    # ---------------------------------
    # def _remove_items(self, items):
    #     if not items:
    #         return
    #     root_item = self.invisibleRootItem()
    #     for item in items:
    #         row = item.row()
    #         if row < 0:
    #             continue
    #         parent = item.parent()
    #         if parent is None:
    #             parent = root_item
    #         parent.removeRow(row)
    #
    # def _remove_group_items(self, group_names):
    #     group_items = [
    #         self._group_items_by_name.pop(group_name)
    #         for group_name in group_names
    #     ]
    #     self._remove_items(group_items)
    #
    # def _remove_merged_items(self, paths):
    #     merged_items = [
    #         self._merged_items_by_id.pop(path)
    #         for path in paths
    #     ]
    #     self._remove_items(merged_items)
    #
    # def _remove_product_items(self, product_ids):
    #     product_items = []
    #     for product_id in product_ids:
    #         self._product_items_by_id.pop(product_id)
    #         product_items.append(self._items_by_id.pop(product_id))
    #     self._remove_items(product_items)
    #
    # def _add_to_new_items(self, item, parent_item, new_items, root_item):
    #     if item.row() < 0:
    #         new_items.append(item)
    #     else:
    #         item_parent = item.parent()
    #         if item_parent is not parent_item:
    #             if item_parent is None:
    #                 item_parent = root_item
    #             item_parent.takeRow(item.row())
    #             new_items.append(item)

    # def refresh(self, project_name, folder_ids):
    #     product_items = self._controller.get_product_items(
    #         project_name,
    #         folder_ids,
    #         sender=PRODUCTS_MODEL_SENDER_NAME
    #     )
    #     product_items_by_id = {
    #         product_item.product_id: product_item
    #         for product_item in product_items
    #     }
    #     # Remove product items that are not available
    #     product_ids_to_remove = (
    #         set(self._items_by_id.keys()) - set(product_items_by_id.keys())
    #     )
    #     self._remove_product_items(product_ids_to_remove)
    #
    #     # Prepare product groups
    #     product_name_matches_by_group = collections.defaultdict(dict)
    #     for product_item in product_items_by_id.values():
    #         group_name = None
    #         if self._grouping_enabled:
    #             group_name = product_item.group_name
    #
    #         product_name = product_item.product_name
    #         group = product_name_matches_by_group[group_name]
    #         if product_name not in group:
    #             group[product_name] = [product_item]
    #             continue
    #         group[product_name].append(product_item)
    #
    #     group_names = set(product_name_matches_by_group.keys())
    #
    #     root_item = self.invisibleRootItem()
    #     new_root_items = []
    #     merged_paths = set()
    #     for group_name in group_names:
    #         key_parts = []
    #         if group_name:
    #             key_parts.append(group_name)
    #
    #         groups = product_name_matches_by_group[group_name]
    #         merged_product_items = {}
    #         top_items = []
    #         for product_name, product_items in groups.items():
    #             if len(product_items) == 1:
    #                 top_items.append(product_items[0])
    #             else:
    #                 path = "/".join(key_parts + [product_name])
    #                 merged_paths.add(path)
    #                 merged_product_items[path] = product_items
    #
    #         parent_item = None
    #         if group_name:
    #             parent_item = self._get_group_model_item(group_name)
    #
    #         new_items = []
    #         if parent_item is not None and parent_item.row() < 0:
    #             new_root_items.append(parent_item)
    #
    #         for product_item in top_items:
    #             item = self._get_product_model_item(product_item)
    #             self._add_to_new_items(
    #                 item, parent_item, new_items, root_item
    #             )
    #
    #         for path, product_items in merged_product_items.items():
    #             merged_item = self._get_merged_model_item(path)
    #             self._add_to_new_items(
    #                 merged_item, parent_item, new_items, root_item
    #             )
    #
    #             new_merged_items = []
    #             for product_item in product_items:
    #                 item = self._get_product_model_item(product_item)
    #                 self._add_to_new_items(
    #                     item, merged_item, new_merged_items, root_item
    #                 )
    #
    #             if new_merged_items:
    #                 merged_item.appendRows(new_merged_items)
    #
    #         if not new_items:
    #             continue
    #
    #         if parent_item is not None:
    #             parent_item.appendRows(new_items)
    #             continue
    #
    #         new_root_items.extend(new_items)
    #
    #     root_item.appendRows(new_root_items)
    #
    #     merged_item_ids_to_remove = (
    #         set(self._merged_items_by_id.keys()) - merged_paths
    #     )
    #     group_names_to_remove = (
    #         set(self._group_items_by_name.keys()) - set(group_names)
    #     )
    #     self._remove_merged_items(merged_item_ids_to_remove)
    #     self._remove_group_items(group_names_to_remove)
