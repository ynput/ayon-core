import re
import logging

import collections

from qtpy import QtCore, QtGui
import qtawesome

from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.lib import format_version

ITEM_ID_ROLE = QtCore.Qt.UserRole + 1
NAME_COLOR_ROLE = QtCore.Qt.UserRole + 2
COUNT_ROLE = QtCore.Qt.UserRole + 3
IS_CONTAINER_ITEM_ROLE = QtCore.Qt.UserRole + 4
VERSION_IS_LATEST_ROLE = QtCore.Qt.UserRole + 5
VERSION_IS_HERO_ROLE = QtCore.Qt.UserRole + 6
VERSION_LABEL_ROLE = QtCore.Qt.UserRole + 7
VERSION_COLOR_ROLE = QtCore.Qt.UserRole + 8
STATUS_NAME_ROLE = QtCore.Qt.UserRole + 9
STATUS_COLOR_ROLE = QtCore.Qt.UserRole + 10
STATUS_SHORT_ROLE = QtCore.Qt.UserRole + 11
STATUS_ICON_ROLE = QtCore.Qt.UserRole + 12
PRODUCT_ID_ROLE = QtCore.Qt.UserRole + 13
PRODUCT_TYPE_ROLE = QtCore.Qt.UserRole + 14
PRODUCT_TYPE_ICON_ROLE = QtCore.Qt.UserRole + 15
PRODUCT_GROUP_NAME_ROLE = QtCore.Qt.UserRole + 16
PRODUCT_GROUP_ICON_ROLE = QtCore.Qt.UserRole + 17
LOADER_NAME_ROLE = QtCore.Qt.UserRole + 18
OBJECT_NAME_ROLE = QtCore.Qt.UserRole + 19
ACTIVE_SITE_PROGRESS_ROLE = QtCore.Qt.UserRole + 20
REMOTE_SITE_PROGRESS_ROLE = QtCore.Qt.UserRole + 21
ACTIVE_SITE_ICON_ROLE = QtCore.Qt.UserRole + 22
REMOTE_SITE_ICON_ROLE = QtCore.Qt.UserRole + 23
# This value hold unique value of container that should be used to identify
#     containers inbetween refresh.
ITEM_UNIQUE_NAME_ROLE = QtCore.Qt.UserRole + 24


class InventoryModel(QtGui.QStandardItemModel):
    """The model for the inventory"""

    column_labels = [
        "Name",
        "Version",
        "Status",
        "Count",
        "Product type",
        "Group",
        "Loader",
        "Object name",
        "Active site",
        "Remote site",
    ]
    name_col = column_labels.index("Name")
    version_col = column_labels.index("Version")
    status_col = column_labels.index("Status")
    count_col = column_labels.index("Count")
    product_type_col = column_labels.index("Product type")
    product_group_col = column_labels.index("Group")
    loader_col = column_labels.index("Loader")
    object_name_col = column_labels.index("Object name")
    active_site_col = column_labels.index("Active site")
    remote_site_col = column_labels.index("Remote site")
    display_role_by_column = {
        name_col: QtCore.Qt.DisplayRole,
        version_col: VERSION_LABEL_ROLE,
        status_col: STATUS_NAME_ROLE,
        count_col: COUNT_ROLE,
        product_type_col: PRODUCT_TYPE_ROLE,
        product_group_col: PRODUCT_GROUP_NAME_ROLE,
        loader_col: LOADER_NAME_ROLE,
        object_name_col: OBJECT_NAME_ROLE,
        active_site_col: ACTIVE_SITE_PROGRESS_ROLE,
        remote_site_col: REMOTE_SITE_PROGRESS_ROLE,
    }
    decoration_role_by_column = {
        name_col: QtCore.Qt.DecorationRole,
        product_type_col: PRODUCT_TYPE_ICON_ROLE,
        product_group_col: PRODUCT_GROUP_ICON_ROLE,
        active_site_col: ACTIVE_SITE_ICON_ROLE,
        remote_site_col: REMOTE_SITE_ICON_ROLE,
    }
    foreground_role_by_column = {
        name_col: NAME_COLOR_ROLE,
        version_col: VERSION_COLOR_ROLE,
        status_col: STATUS_COLOR_ROLE
    }
    width_by_column = {
        name_col: 250,
        version_col: 55,
        status_col: 100,
        count_col: 55,
        product_type_col: 150,
        product_group_col: 120,
        loader_col: 150,
    }

    OUTDATED_COLOR = QtGui.QColor(235, 30, 30)
    CHILD_OUTDATED_COLOR = QtGui.QColor(200, 160, 30)
    GRAYOUT_COLOR = QtGui.QColor(160, 160, 160)

    def __init__(self, controller, parent=None):
        super().__init__(parent)

        self.setColumnCount(len(self.column_labels))
        for idx, label in enumerate(self.column_labels):
            self.setHeaderData(idx, QtCore.Qt.Horizontal, label)

        self.log = logging.getLogger(self.__class__.__name__)

        self._controller = controller

        self._hierarchy_view = False

        self._default_icon_color = get_default_entity_icon_color()

        self._last_project_statuses = {}
        self._last_status_icons_by_name = {}

    def outdated(self, item):
        return item.get("isOutdated", True)

    def refresh(self, selected=None):
        """Refresh the model"""
        # for debugging or testing, injecting items from outside
        container_items = self._controller.get_container_items()

        self._clear_items()

        items_by_repre_id = {}
        for container_item in container_items:
            # if (
            #     selected is not None
            #     and container_item.item_id not in selected
            # ):
            #     continue
            repre_id = container_item.representation_id
            items = items_by_repre_id.setdefault(repre_id, [])
            items.append(container_item)

        repre_id = set(items_by_repre_id.keys())
        repre_info_by_id = self._controller.get_representation_info_items(
            repre_id
        )
        product_ids = {
            repre_info.product_id
            for repre_info in repre_info_by_id.values()
        }
        version_items_by_product_id = self._controller.get_version_items(
            product_ids
        )
        # SiteSync addon information
        progress_by_id = self._controller.get_representations_site_progress(
            repre_id
        )
        sites_info = self._controller.get_sites_information()
        site_icons = {
            provider: get_qt_icon(icon_def)
            for provider, icon_def in (
                self._controller.get_site_provider_icons().items()
            )
        }
        self._last_project_statuses = {
            status_item.name: status_item
            for status_item in self._controller.get_project_status_items()
        }
        self._last_status_icons_by_name = {}

        group_item_icon = qtawesome.icon(
            "fa.folder", color=self._default_icon_color
        )
        valid_item_icon = qtawesome.icon(
            "fa.file-o", color=self._default_icon_color
        )
        invalid_item_icon = qtawesome.icon(
            "fa.exclamation-circle", color=self._default_icon_color
        )
        group_icon = qtawesome.icon(
            "fa.object-group", color=self._default_icon_color
        )
        product_type_icon = qtawesome.icon(
            "fa.folder", color="#0091B2"
        )
        group_item_font = QtGui.QFont()
        group_item_font.setBold(True)

        active_site_icon = site_icons.get(sites_info["active_site_provider"])
        remote_site_icon = site_icons.get(sites_info["remote_site_provider"])

        root_item = self.invisibleRootItem()
        group_items = []
        for repre_id, container_items in items_by_repre_id.items():
            repre_info = repre_info_by_id[repre_id]
            version_label = "N/A"
            version_color = None
            is_latest = False
            is_hero = False
            status_name = None
            if not repre_info.is_valid:
                group_name = "< Entity N/A >"
                item_icon = invalid_item_icon

            else:
                group_name = "{}_{}: ({})".format(
                    repre_info.folder_path.rsplit("/")[-1],
                    repre_info.product_name,
                    repre_info.representation_name
                )
                item_icon = valid_item_icon

                version_items = (
                    version_items_by_product_id[repre_info.product_id]
                )
                version_item = version_items[repre_info.version_id]
                version_label = format_version(version_item.version)
                is_hero = version_item.version < 0
                is_latest = version_item.is_latest
                if not is_latest:
                    version_color = self.OUTDATED_COLOR
                status_name = version_item.status

            status_color, status_short, status_icon = self._get_status_data(
                status_name
            )

            container_model_items = []
            for container_item in container_items:
                unique_name = (
                    repre_info.representation_name
                    + container_item.object_name or "<none>"
                )

                item = QtGui.QStandardItem()
                item.setColumnCount(root_item.columnCount())
                item.setData(container_item.namespace, QtCore.Qt.DisplayRole)
                item.setData(self.GRAYOUT_COLOR, NAME_COLOR_ROLE)
                item.setData(self.GRAYOUT_COLOR, VERSION_COLOR_ROLE)
                item.setData(item_icon, QtCore.Qt.DecorationRole)
                item.setData(repre_info.product_id, PRODUCT_ID_ROLE)
                item.setData(container_item.item_id, ITEM_ID_ROLE)
                item.setData(version_label, VERSION_LABEL_ROLE)
                item.setData(container_item.loader_name, LOADER_NAME_ROLE)
                item.setData(container_item.object_name, OBJECT_NAME_ROLE)
                item.setData(True, IS_CONTAINER_ITEM_ROLE)
                item.setData(unique_name, ITEM_UNIQUE_NAME_ROLE)
                container_model_items.append(item)

            if not container_model_items:
                continue

            progress = progress_by_id[repre_id]
            active_site_progress = "{}%".format(
                max(progress["active_site"], 0) * 100
            )
            remote_site_progress = "{}%".format(
                max(progress["remote_site"], 0) * 100
            )

            group_item = QtGui.QStandardItem()
            group_item.setColumnCount(root_item.columnCount())
            group_item.setData(group_name, QtCore.Qt.DisplayRole)
            group_item.setData(group_name, ITEM_UNIQUE_NAME_ROLE)
            group_item.setData(group_item_icon, QtCore.Qt.DecorationRole)
            group_item.setData(group_item_font, QtCore.Qt.FontRole)
            group_item.setData(repre_info.product_id, PRODUCT_ID_ROLE)
            group_item.setData(repre_info.product_type, PRODUCT_TYPE_ROLE)
            group_item.setData(product_type_icon, PRODUCT_TYPE_ICON_ROLE)
            group_item.setData(is_latest, VERSION_IS_LATEST_ROLE)
            group_item.setData(is_hero, VERSION_IS_HERO_ROLE)
            group_item.setData(version_label, VERSION_LABEL_ROLE)
            group_item.setData(len(container_items), COUNT_ROLE)
            group_item.setData(status_name, STATUS_NAME_ROLE)
            group_item.setData(status_short, STATUS_SHORT_ROLE)
            group_item.setData(status_color, STATUS_COLOR_ROLE)
            group_item.setData(status_icon, STATUS_ICON_ROLE)

            group_item.setData(
                active_site_progress, ACTIVE_SITE_PROGRESS_ROLE
            )
            group_item.setData(
                remote_site_progress, REMOTE_SITE_PROGRESS_ROLE
            )
            group_item.setData(active_site_icon, ACTIVE_SITE_ICON_ROLE)
            group_item.setData(remote_site_icon, REMOTE_SITE_ICON_ROLE)
            group_item.setData(False, IS_CONTAINER_ITEM_ROLE)

            if version_color is not None:
                group_item.setData(version_color, VERSION_COLOR_ROLE)

            if repre_info.product_group:
                group_item.setData(
                    repre_info.product_group, PRODUCT_GROUP_NAME_ROLE
                )
                group_item.setData(group_icon, PRODUCT_GROUP_ICON_ROLE)

            group_item.appendRows(container_model_items)
            group_items.append(group_item)

        if group_items:
            root_item.appendRows(group_items)

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index, role):
        if not index.isValid():
            return

        col = index.column()
        if role == QtCore.Qt.DisplayRole:
            role = self.display_role_by_column.get(col)
            if role is None:
                print(col, role)
                return None

        elif role == QtCore.Qt.DecorationRole:
            role = self.decoration_role_by_column.get(col)
            if role is None:
                return None

        elif role == QtCore.Qt.ForegroundRole:
            role = self.foreground_role_by_column.get(col)
            if role is None:
                return None

        if col != 0:
            index = self.index(index.row(), 0, index.parent())

        return super().data(index, role)

    def set_hierarchy_view(self, state):
        """Set whether to display products in hierarchy view."""
        state = bool(state)

        if state != self._hierarchy_view:
            self._hierarchy_view = state

    def get_outdated_item_ids(self, ignore_hero=True):
        outdated_item_ids = []
        root_item = self.invisibleRootItem()
        for row in range(root_item.rowCount()):
            group_item = root_item.child(row)
            if group_item.data(VERSION_IS_LATEST_ROLE):
                continue

            if ignore_hero and group_item.data(VERSION_IS_HERO_ROLE):
                continue

            for idx in range(group_item.rowCount()):
                item = group_item.child(idx)
                outdated_item_ids.append(item.data(ITEM_ID_ROLE))
        return outdated_item_ids

    def _clear_items(self):
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

    def _get_status_data(self, status_name):
        status_item = self._last_project_statuses.get(status_name)
        status_icon = self._get_status_icon(status_name, status_item)
        status_color = status_short = None
        if status_item is not None:
            status_color = status_item.color
            status_short = status_item.short
        return status_color, status_short, status_icon

    def _get_status_icon(self, status_name, status_item):
        icon = self._last_status_icons_by_name.get(status_name)
        if icon is not None:
            return icon

        icon = None
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


class FilterProxyModel(QtCore.QSortFilterProxyModel):
    """Filter model to where key column's value is in the filtered tags"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._filter_outdated = False
        self._hierarchy_view = False

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        source_index = model.index(row, self.filterKeyColumn(), parent)

        # Always allow bottom entries (individual containers), since their
        # parent group hidden if it wouldn't have been validated.
        if source_index.data(IS_CONTAINER_ITEM_ROLE):
            return True

        if self._filter_outdated:
            # When filtering to outdated we filter the up to date entries
            # thus we "allow" them when they are outdated
            if source_index.data(VERSION_IS_LATEST_ROLE):
                return False

        # Filter by regex
        if hasattr(self, "filterRegularExpression"):
            regex = self.filterRegularExpression()
        else:
            regex = self.filterRegExp()

        if not self._matches(row, parent, regex.pattern()):
            return False
        return True

    def set_filter_outdated(self, state):
        """Set whether to show the outdated entries only."""
        state = bool(state)

        if state != self._filter_outdated:
            self._filter_outdated = bool(state)
            self.invalidateFilter()

    def set_hierarchy_view(self, state):
        state = bool(state)

        if state != self._hierarchy_view:
            self._hierarchy_view = state

    def _matches(self, row, parent, pattern):
        """Return whether row matches regex pattern.

        Args:
            row (int): row number in model
            parent (QtCore.QModelIndex): parent index
            pattern (regex.pattern): pattern to check for in key

        Returns:
            bool

        """
        if not pattern:
            return True

        flags = 0
        if self.sortCaseSensitivity() == QtCore.Qt.CaseInsensitive:
            flags = re.IGNORECASE

        regex = re.compile(re.escape(pattern), flags=flags)

        model = self.sourceModel()
        column = self.filterKeyColumn()
        role = self.filterRole()

        matches_queue = collections.deque()
        matches_queue.append((row, parent))
        while matches_queue:
            queue_item = matches_queue.popleft()
            row, parent = queue_item

            index = model.index(row, column, parent)
            value = model.data(index, role)
            if regex.search(value):
                return True

            for idx in range(model.rowCount(index)):
                matches_queue.append((idx, index))

        return False
