from __future__ import annotations

from collections import deque, defaultdict

from qtpy.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from qtpy.QtGui import QStandardItemModel, QStandardItem

from ayon_core.lib import MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon

from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue

FOLDER_ID_ROLE = Qt.UserRole + 1
FOLDER_NAME_ROLE = Qt.UserRole + 2
FOLDER_PATH_ROLE = Qt.UserRole + 3
FOLDER_TYPE_ROLE = Qt.UserRole + 4
FOLDER_STATUS_ROLE = Qt.UserRole + 5
FOLDER_STATUS_ICON_ROLE = Qt.UserRole + 6
FOLDER_PATH_FILTER_ROLE = Qt.UserRole + 7
FOLDERS_MODEL_SENDER_NAME = "qt_folders_model"


class BrowserFoldersProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setRecursiveFilteringEnabled(True)

        self._folder_ids_filter = None
        self._name_filter_terms = []

    def set_name_filter(self, name: str) -> None:
        self._name_filter_terms = name.casefold().split()
        self.invalidateFilter()

    def _match_name_filter(self, source_index) -> bool:
        if not self._name_filter_terms:
            return True
        folder_path_filter = source_index.data(FOLDER_PATH_FILTER_ROLE)
        if not folder_path_filter:
            return False
        return all(
            term in folder_path_filter for term in self._name_filter_terms
        )

    def set_folder_ids_filter(self, folder_ids: set[str] | None):
        if self._folder_ids_filter == folder_ids:
            return
        self._folder_ids_filter = folder_ids
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent_index):
        source_index = self.sourceModel().index(row, 0, parent_index)
        if self._folder_ids_filter is not None:
            if not self._folder_ids_filter:
                return False
            folder_id = source_index.data(FOLDER_ID_ROLE)
            if folder_id not in self._folder_ids_filter:
                return False

        if not self._match_name_filter(source_index):
            return False

        return super().filterAcceptsRow(row, parent_index)


class BrowserFoldersModel(QStandardItemModel):
    """Folders model which cares about refresh of folders.

    Args:
        controller: The control object.
        The model contains both **Folders** and **Status** columns.
        Visibility of the status column is controlled by the view.
    """
    _default_folder_icon = None

    FILTER_ROLE = FOLDER_PATH_FILTER_ROLE

    def __init__(self, ui_controller, controller):
        super().__init__()

        self.setColumnCount(2)
        self.setHeaderData(0, Qt.Horizontal, "Folders")
        self.setHeaderData(1, Qt.Horizontal, "")

        self._ui_controller = ui_controller
        self._controller = controller
        self._items_by_id = {}
        self._parent_id_by_id = {}

        self._last_project_name = None
        self._context_id: str = f"ltm_{id(self)}_v0"

    def reset(self):
        """Refresh folders for last selected project.

        Force to update folders model from controller. This may or may not
        trigger query from server, that's based on controller's cache.
        """
        project_name = self._ui_controller.current_project
        if not project_name:
            self._last_project_name = project_name
            self._fill_items({}, {}, [])
            return

        if self._last_project_name != project_name:
            self._clear_items()
        self._last_project_name = project_name
        task = AsyncTask(
            name="fetch_all_folders",
            function=self._fetch_folders_data,
            callback=self._on_data_fetched,
            # Lower priority than per-node fetches so an expand click
            # the user makes while the bulk fetch is still running is
            # never held up behind it.
            priority=5,
            context_id=self._context_id,
            cancellable=True,
        )
        get_task_queue().enqueue(task)

    def get_index_by_id(self, item_id):
        """Get index by folder id.

        Returns:
            QModelIndex: Index of the folder. Can be invalid if folder
                is not available.
        """
        item = self._items_by_id.get(item_id)
        if item is None:
            return QModelIndex()
        return self.indexFromItem(item)

    def _clear_items(self):
        self._items_by_id = {}
        self._parent_id_by_id = {}
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

    def _fetch_folders_data(self):
        project_name = self._ui_controller.current_project
        folder_items = self._controller.get_folder_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        folder_type_items = self._controller.get_folder_type_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        status_items = self._controller.get_project_status_items(
            project_name, sender=FOLDERS_MODEL_SENDER_NAME
        )
        return folder_items, folder_type_items, status_items

    def _on_data_fetched(self, result):
        """Callback when refresh thread is finished.

        Technically can be running multiple refresh threads at the same time,
        to avoid using values from wrong thread, we check if thread id is
        current refresh thread id.

        Folders are stored by id.

        Args:
            result (tuple): Result from refresh.

        """
        self._fill_items(*result)

    def _get_folder_item_icon(
        self,
        folder_item,
        folder_type_item_by_name,
        folder_type_icon_cache
    ):
        icon = folder_type_icon_cache.get(folder_item.folder_type)
        if icon is not None:
            return icon

        folder_type_item = folder_type_item_by_name.get(
            folder_item.folder_type
        )
        icon_name = color = None
        if folder_type_item is not None:
            icon_name = folder_type_item.icon
            color = folder_type_item.color
        icon = get_qt_icon(MaterialSymbolsIcon(
            icon_name or "folder",
            color=color or get_default_entity_icon_color(),
        ))

        folder_type_icon_cache[folder_item.folder_type] = icon
        return icon

    def _fill_item_data(
        self,
        item,
        folder_item,
        folder_type_item_by_name,
        folder_type_icon_cache,
        status_icon_by_name,
        folder_label_path,
    ):
        """

        Args:
            item (QtGui.QStandardItem): Item to fill data.
            folder_item (FolderItem): Folder item.
            folder_type_item_by_name: Mapping of folder type names to items.
            folder_type_icon_cache: Cache for folder type icons.
            status_icon_by_name: Mapping of status name to QIcon.

        """
        icon = self._get_folder_item_icon(
            folder_item,
            folder_type_item_by_name,
            folder_type_icon_cache
        )
        item.setData(folder_item.entity_id, FOLDER_ID_ROLE)
        item.setData(folder_item.name, FOLDER_NAME_ROLE)
        item.setData(folder_item.path, FOLDER_PATH_ROLE)
        item.setData(folder_item.folder_type, FOLDER_TYPE_ROLE)
        item.setData(folder_item.label, Qt.DisplayRole)
        item.setData(icon, Qt.DecorationRole)
        item.setData(folder_item.status, FOLDER_STATUS_ROLE)
        status_icon = status_icon_by_name.get(folder_item.status)
        item.setData(status_icon, FOLDER_STATUS_ICON_ROLE)
        folder_path_filter = f"{folder_item.path} {folder_label_path}"
        item.setData(folder_path_filter.casefold(), FOLDER_PATH_FILTER_ROLE)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if index.column() != 0:
            return self._get_index_data(index, role)

        return super().data(index, role)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() != 0:
            return self._get_index_flags(index)
        return super().flags(index)

    def _get_index_flags(self, index):
        index = index.sibling(index.row(), 0)
        return super().flags(index)

    def _get_index_data(self, index, role):
        """Get data for index with column 1 or higher.

        Allow classes inheriting from this class to change the 'data' method
            behavior. Without this they can't use 'super' call.

        """
        index = index.sibling(index.row(), 0)
        if role == Qt.DecorationRole:
            role = FOLDER_STATUS_ICON_ROLE
        elif role == Qt.ToolTipRole:
            role = FOLDER_STATUS_ROLE
        elif role < Qt.UserRole:
            return None
        return super().data(index, role)

    def _fill_items(self, folder_items_by_id, folder_type_items, status_items):
        if not folder_items_by_id:
            if folder_items_by_id is not None:
                self._clear_items()
            return

        self.beginResetModel()
        folder_type_item_by_name = {
            folder_type.name: folder_type
            for folder_type in folder_type_items
        }
        folder_type_icon_cache = {}

        # Build a local status-icon lookup for this fill operation
        status_icon_by_name = {}
        for status in status_items:
            icon = None
            if status.icon:
                icon = get_qt_icon(
                    MaterialSymbolsIcon(status.icon, color=status.color)
                )
            status_icon_by_name[status.name] = icon

        folder_ids = set(folder_items_by_id)
        ids_to_remove = set(self._items_by_id) - folder_ids

        folder_items_by_parent = defaultdict(dict)
        for folder_item in folder_items_by_id.values():
            (
                folder_items_by_parent
                [folder_item.parent_id]
                [folder_item.entity_id]
            ) = folder_item

        hierarchy_queue = deque()
        hierarchy_queue.append((self.invisibleRootItem(), None, ""))

        # Keep pointers to removed items until the refresh finishes
        #   - some children of the items could be moved and reused elsewhere
        removed_items = []
        while hierarchy_queue:
            item = hierarchy_queue.popleft()
            parent_item, parent_id, parent_path = item
            folder_items = folder_items_by_parent[parent_id]

            items_by_id = {}
            folder_ids_to_add = set(folder_items)
            for row_idx in reversed(range(parent_item.rowCount())):
                child_item = parent_item.child(row_idx)
                child_id = child_item.data(FOLDER_ID_ROLE)
                if child_id in ids_to_remove:
                    removed_items.append(parent_item.takeRow(row_idx))
                else:
                    items_by_id[child_id] = child_item

            new_items = []
            for item_id in folder_ids_to_add:
                folder_item = folder_items[item_id]
                item = items_by_id.get(item_id)
                if item is None:
                    is_new = True
                    item = QStandardItem()
                    item.setEditable(False)
                else:
                    is_new = self._parent_id_by_id[item_id] != parent_id

                folder_label_path = f"{parent_path}/{folder_item.label}"
                self._fill_item_data(
                    item,
                    folder_item,
                    folder_type_item_by_name,
                    folder_type_icon_cache,
                    status_icon_by_name,
                    folder_label_path,
                )
                if is_new:
                    item.setColumnCount(self.columnCount())
                    new_items.append(item)
                self._items_by_id[item_id] = item
                self._parent_id_by_id[item_id] = parent_id

                hierarchy_queue.append((item, item_id, folder_label_path))

            if new_items:
                parent_item.appendRows(new_items)

        for item_id in ids_to_remove:
            self._items_by_id.pop(item_id)
            self._parent_id_by_id.pop(item_id)

        self.endResetModel()
