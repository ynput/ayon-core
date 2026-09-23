from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque, defaultdict
import typing
from typing import Any

from qtpy.QtCore import (
    Signal,
    Qt,
    QSortFilterProxyModel,
    QModelIndex,
    QPersistentModelIndex,
)
from qtpy.QtGui import QStandardItemModel, QStandardItem, QIcon

from ayon_core.lib import MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon

from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models import (
        StatusItem,
        FolderItem,
        FolderTypeItem,
    )

    from .browser_controller import (
        BrowserController,
        BrowserWidgetController,
    )

FOLDER_ID_ROLE = Qt.ItemDataRole.UserRole + 1
FOLDER_NAME_ROLE = Qt.ItemDataRole.UserRole + 2
FOLDER_PATH_ROLE = Qt.ItemDataRole.UserRole + 3
FOLDER_TYPE_ROLE = Qt.ItemDataRole.UserRole + 4
FOLDER_STATUS_ROLE = Qt.ItemDataRole.UserRole + 5
FOLDER_STATUS_ICON_ROLE = Qt.ItemDataRole.UserRole + 6
FOLDER_PATH_FILTER_ROLE = Qt.ItemDataRole.UserRole + 7
FOLDERS_MODEL_SENDER_NAME = "qt_folders_model"


@dataclass(frozen=True)
class FetchData:
    project_name: str
    folder_items_by_id: dict[str, FolderItem]
    folder_type_items: list[FolderTypeItem]
    status_items: list[StatusItem]


@dataclass(frozen=True)
class FillFolderItem:
    __slots__ = (
        "item",
        "parent_id",
        "name",
        "path",
        "label",
        "folder_type",
        "status",
        "path_filter",
    )
    item: QStandardItem
    parent_id: str | None
    name: str
    path: str
    label: str
    folder_type: str
    status: str
    path_filter: str

    @classmethod
    def from_folder_item(
        cls, item: QStandardItem, folder_item: FolderItem, label_path: str
    ) -> FillFolderItem:
        return cls(
            item=item,
            parent_id=folder_item.parent_id,
            name=folder_item.name,
            path=folder_item.path,
            label=folder_item.label,
            folder_type=folder_item.folder_type,
            status=folder_item.status,
            path_filter=f"{folder_item.path} {label_path}".casefold(),
        )


@dataclass
class _FillData:
    project_name: str | None = None
    folder_types_by_name: dict[str, FolderTypeItem] = field(
        default_factory=dict
    )
    statuses_by_name: dict[str, StatusItem] = field(default_factory=dict)
    items_by_id: dict[str, FillFolderItem] = field(default_factory=dict)


class BrowserFoldersModel(QStandardItemModel):
    """Folders model which cares about refresh of folders.

    Args:
        ui_controller (BrowserWidgetController): The Browser UI controller.
        controller (BrowserController): The Browser controller.
    """
    _default_folder_icon = None

    reset_finished = Signal()

    def __init__(
        self,
        ui_controller: BrowserWidgetController,
        be_controller: BrowserController,
    ) -> None:
        super().__init__()

        self.setColumnCount(2)
        self.setHeaderData(0, Qt.Orientation.Horizontal, "Folders")
        self.setHeaderData(1, Qt.Orientation.Horizontal, "")

        self._ui_controller = ui_controller
        self._be_controller = be_controller
        self._fill_data = _FillData()

        self._last_project_name = None
        self._context_id: str = f"folders_model_{id(self)}_v0"

    def reset(self):
        """Refresh folders for last selected project.

        Force to update folders model from controller. This may or may not
        trigger query from server, that's based on controller's cache.
        """
        project_name = self._ui_controller.current_project
        if not project_name:
            self._last_project_name = project_name
            self._fill_items(
                project_name, {}, [], []
            )
            return

        if self._last_project_name != project_name:
            self._clear_items()
        self._last_project_name = project_name
        task = AsyncTask(
            name="fetch_all_folders",
            function=lambda: self._fetch_folders_data(project_name),
            callback=self._on_data_fetched,
            priority=5,
            context_id=self._context_id,
            cancellable=True,
        )
        get_task_queue().enqueue(task)

    def get_index_by_id(self, item_id: str) -> QModelIndex:
        """Get index by folder id.

        Returns:
            QModelIndex: Index of the folder. Can be invalid if folder
                is not available.
        """
        fill_item = self._fill_data.items_by_id.get(item_id)
        if fill_item is None:
            return QModelIndex()
        return self.indexFromItem(fill_item.item)

    def _clear_items(self) -> None:
        self._fill_data = _FillData()
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

    def _fetch_folders_data(
        self, project_name: str
    ) -> FetchData:
        folder_items = self._be_controller.get_folder_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        folder_type_items = self._be_controller.get_folder_type_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        status_items = self._be_controller.get_project_status_items(
            project_name, sender=FOLDERS_MODEL_SENDER_NAME
        )
        return FetchData(
            project_name=project_name,
            folder_items_by_id=folder_items,
            folder_type_items=folder_type_items,
            status_items=status_items,
        )

    def _on_data_fetched(self, result: FetchData) -> None:
        """Callback when refresh thread is finished.

        Technically can be running multiple refresh threads at the same time,
        to avoid using values from wrong thread, we check if thread id is
        current refresh thread id.

        Folders are stored by id.

        Args:
            result (FetchData): Result from refresh.

        """
        if self._last_project_name != result.project_name:
            return

        self._fill_items(
            result.project_name,
            result.folder_items_by_id,
            result.folder_type_items,
            result.status_items,
        )

    def _get_folder_item_icon(
        self,
        folder_type: str,
        folder_type_icons_by_name: dict[str, QIcon | None],
    ) -> QIcon:
        icon = folder_type_icons_by_name.get(folder_type)
        if icon is None:
            icon = get_qt_icon(MaterialSymbolsIcon(
                "folder", get_default_entity_icon_color(),
            ))
            folder_type_icons_by_name[folder_type] = icon
        return icon

    def _fill_item_data(
        self,
        item: QStandardItem,
        folder_item: FolderItem,
        folder_type_icons_by_name: dict[str, QIcon | None],
        status_icon_by_name: dict[str, QIcon | None],
        folder_label_path: str,
    ) -> None:
        """

        Args:
            item (QtGui.QStandardItem): Item to fill data.
            folder_item (FolderItem): Folder item.
            folder_type_icons_by_name: Cache for folder type icons.
            status_icon_by_name: Mapping of status name to QIcon.

        """
        icon = self._get_folder_item_icon(
            folder_item.folder_type,
            folder_type_icons_by_name,
        )
        item.setData(folder_item.entity_id, FOLDER_ID_ROLE)
        item.setData(folder_item.name, FOLDER_NAME_ROLE)
        item.setData(folder_item.path, FOLDER_PATH_ROLE)
        item.setData(folder_item.folder_type, FOLDER_TYPE_ROLE)
        item.setData(folder_item.label, Qt.ItemDataRole.DisplayRole)
        item.setData(icon, Qt.ItemDataRole.DecorationRole)
        item.setData(folder_item.status, FOLDER_STATUS_ROLE)
        status_icon = status_icon_by_name.get(folder_item.status)
        item.setData(status_icon, FOLDER_STATUS_ICON_ROLE)
        folder_path_filter = f"{folder_item.path} {folder_label_path}"
        item.setData(folder_path_filter.casefold(), FOLDER_PATH_FILTER_ROLE)

    def _update_item_data(
        self,
        statuses_changed: bool,
        folder_types_changed: bool,
        old_fill_item: FillFolderItem,
        new_fill_item: FillFolderItem,
        folder_type_icons_by_name: dict[str, QIcon | None],
        status_icon_by_name: dict[str, QIcon | None],
    ) -> None:
        """

        Args:
            statuses_changed (bool): Whether the statuses have changed.
            folder_types_changed (bool): Whether the product types have changed.
            old_fill_item (FillFolderItem): Old fill folder item.
            new_fill_item (FillFolderItem): New fill folder item.
            folder_type_icons_by_name: Cache for folder type icons.
            status_icon_by_name: Mapping of status name to QIcon.

        """
        item = old_fill_item.item
        update_icon = folder_types_changed
        if new_fill_item.folder_type != old_fill_item.folder_type:
            update_icon = True
            item.setData(new_fill_item.folder_type, FOLDER_TYPE_ROLE)

        if update_icon:
            icon = self._get_folder_item_icon(
                new_fill_item.folder_type,
                folder_type_icons_by_name,
            )
            item.setData(icon, Qt.ItemDataRole.DecorationRole)

        update_status_icon = statuses_changed
        if new_fill_item.status != old_fill_item.status:
            update_status_icon = True
            item.setData(new_fill_item.status, FOLDER_STATUS_ROLE)

        if update_status_icon:
            status_icon = status_icon_by_name.get(new_fill_item.status)
            item.setData(status_icon, FOLDER_STATUS_ICON_ROLE)

        for new_value, old_value, role in (
            (new_fill_item.name, old_fill_item.name, FOLDER_NAME_ROLE),
            (new_fill_item.path, old_fill_item.path, FOLDER_PATH_ROLE),
            (
                new_fill_item.label,
                old_fill_item.label,
                Qt.ItemDataRole.DisplayRole
            ),
            (
                new_fill_item.path_filter,
                old_fill_item.path_filter,
                FOLDER_PATH_FILTER_ROLE
            ),
        ):
            if new_value != old_value:
                item.setData(new_value, role)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role:int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None

        if index.column() != 0:
            return self._get_index_data(index, role)

        return super().data(index, role)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
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
        if role == Qt.ItemDataRole.DecorationRole:
            role = FOLDER_STATUS_ICON_ROLE
        elif role == Qt.ItemDataRole.ToolTipRole:
            role = FOLDER_STATUS_ROLE
        elif role < Qt.ItemDataRole.UserRole:
            return None
        return super().data(index, role)

    def _fill_items(
        self,
        project_name: str,
        folder_items_by_id: dict[str, FolderItem],
        folder_type_items: list[FolderTypeItem],
        status_items: list[StatusItem],
    ) -> None:
        if not folder_items_by_id:
            if folder_items_by_id is not None:
                self._clear_items()
            return

        fill_data = _FillData(project_name)
        fill_data.folder_types_by_name = {
            folder_type.name: folder_type
            for folder_type in folder_type_items
        }

        folder_type_icons_by_name = {}
        for folder_type_item in folder_type_items:
            icon_name = color = None
            if folder_type_item is not None:
                icon_name = folder_type_item.icon
                color = folder_type_item.color
            icon = get_qt_icon(MaterialSymbolsIcon(
                icon_name or "folder",
                color=color or get_default_entity_icon_color(),
            ))
            folder_type_icons_by_name[folder_type_item.name] = icon

        # Build a local status-icon lookup for this fill operation
        fill_data.statuses_by_name = {
            status.name: status
            for status in status_items
        }
        status_icon_by_name = {}
        for status in status_items:
            icon = None
            if status.icon:
                icon = get_qt_icon(
                    MaterialSymbolsIcon(status.icon, color=status.color)
                )
            status_icon_by_name[status.name] = icon

        # Update items if we already have some, otherwise fill from scratch
        # - Update is slower as it has to compare existing items with new
        #   ones, but it preserves expanded and selected state in the view.
        old_fill_data, self._fill_data = self._fill_data, fill_data
        if old_fill_data.items_by_id:
            self._fill_update(
                fill_data,
                old_fill_data,
                folder_items_by_id,
                folder_type_icons_by_name,
                status_icon_by_name,
            )
        else:
            self._fill_from_scratch(
                fill_data,
                folder_items_by_id,
                folder_type_icons_by_name,
                status_icon_by_name,
            )
        self.reset_finished.emit()

    def _fill_from_scratch(
        self,
        fill_data: _FillData,
        folder_items_by_id: dict[str, FolderItem],
        folder_type_icons_by_name: dict[str, QIcon | None],
        status_icon_by_name: dict[str, QIcon | None],
    ) -> None:
        folder_items_by_parent = defaultdict(list)
        for folder_item in folder_items_by_id.values():
            folder_items_by_parent[folder_item.parent_id].append(folder_item)

        hierarchy_queue = deque()
        hierarchy_queue.append((self.invisibleRootItem(), None, ""))

        while hierarchy_queue:
            item = hierarchy_queue.popleft()
            parent_item, parent_id, parent_path = item
            folder_items = folder_items_by_parent[parent_id]

            new_items = []
            for folder_item in folder_items:
                item_id = folder_item.entity_id
                item = QStandardItem()
                item.setEditable(False)
                item.setColumnCount(self.columnCount())

                folder_label_path = f"{parent_path}/{folder_item.label}"
                self._fill_item_data(
                    item,
                    folder_item,
                    folder_type_icons_by_name,
                    status_icon_by_name,
                    folder_label_path,
                )
                new_items.append(item)
                fill_item = FillFolderItem.from_folder_item(
                    item, folder_item, folder_label_path
                )
                fill_data.items_by_id[item_id] = fill_item

                hierarchy_queue.append((item, item_id, folder_label_path))

            if new_items:
                parent_item.appendRows(new_items)

    def _fill_update(
        self,
        fill_data: _FillData,
        old_fill_data: _FillData,
        folder_items_by_id: dict[str, FolderItem],
        folder_type_icons_by_name: dict[str, QIcon | None],
        status_icon_by_name: dict[str, QIcon | None],
    ) -> None:
        folder_items_by_parent = defaultdict(dict)
        for folder_item in folder_items_by_id.values():
            (
                folder_items_by_parent
                [folder_item.parent_id]
                [folder_item.entity_id]
            ) = folder_item

        # Take items that are not in new folders or have different parent
        removed_items = []
        remove_queue = deque()
        remove_queue.append((self.invisibleRootItem(), None))
        while remove_queue:
            parent_item, parent_id = remove_queue.popleft()
            folder_items = folder_items_by_parent[parent_id]
            for row_idx in reversed(range(parent_item.rowCount())):
                child_item = parent_item.child(row_idx)
                child_id = child_item.data(FOLDER_ID_ROLE)
                if child_id not in folder_items:
                    removed_items.append(parent_item.takeRow(row_idx))
                remove_queue.append((child_item, child_id))

        # Check if statuses or folder types changed to propagate icon changes
        statuses_changed = (
            fill_data.statuses_by_name != old_fill_data.statuses_by_name
        )
        folder_types_changed = fill_data.folder_types_by_name != (
            old_fill_data.folder_types_by_name
        )
        hierarchy_queue = deque()
        hierarchy_queue.append((self.invisibleRootItem(), None, ""))

        # Keep pointers to removed items until the refresh finishes
        #   - some children of the items could be moved and reused elsewhere
        while hierarchy_queue:
            item = hierarchy_queue.popleft()
            parent_item, parent_id, parent_path = item
            folder_items = folder_items_by_parent[parent_id]
            new_items = []
            for item_id, folder_item in folder_items.items():
                folder_label_path = f"{parent_path}/{folder_item.label}"
                fill_item = old_fill_data.items_by_id.get(item_id)
                if fill_item is None:
                    item = QStandardItem()
                    item.setEditable(False)
                    item.setColumnCount(self.columnCount())
                    new_fill_item = FillFolderItem.from_folder_item(
                        item, folder_item, folder_label_path
                    )
                    self._fill_item_data(
                        item,
                        folder_item,
                        folder_type_icons_by_name,
                        status_icon_by_name,
                        folder_label_path,
                    )
                    new_items.append(item)
                else:
                    item = fill_item.item
                    new_fill_item = FillFolderItem.from_folder_item(
                        item, folder_item, folder_label_path
                    )
                    if fill_item.parent_id != parent_id:
                        new_items.append(item)
                    self._update_item_data(
                        statuses_changed,
                        folder_types_changed,
                        fill_item,
                        new_fill_item,
                        folder_type_icons_by_name,
                        status_icon_by_name,
                    )

                fill_data.items_by_id[item_id] = new_fill_item

                hierarchy_queue.append((item, item_id, folder_label_path))

            if new_items:
                parent_item.appendRows(new_items)


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
        if self._folder_ids_filter is None and not self._name_filter_terms:
            return True

        source_index = self.sourceModel().index(row, 0, parent_index)
        if self._folder_ids_filter is not None:
            if not self._folder_ids_filter:
                return False
            folder_id = source_index.data(FOLDER_ID_ROLE)
            if folder_id not in self._folder_ids_filter:
                return False

        if not self._match_name_filter(source_index):
            return False
        return True
