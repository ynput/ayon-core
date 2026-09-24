from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass, field
from functools import partial
import sys
import typing
from typing import Callable, Any, Optional
import traceback

from qtpy import QtWidgets, QtGui, QtCore

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.lib.icon_definitions import (
    AwesomeFontIcon,
    MaterialSymbolsIcon,
)
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.common_models import (
    ProjectsModel,
    HierarchyModel,
    HierarchyExpectedSelection,
)
from ayon_core.ui.components import (
    AYButton,
    AYLineEdit,
    AYTreeView
)

from ayon_core.ui.style_types import get_ayon_style
from ayon_core.ui.variants import QTreeViewVariants
from ayon_core.ui.components.tree_view import CenteredIconDelegate

from .models import RecursiveSortFilterProxyModel
from .lib import get_qt_icon

if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models import (
        StatusItem,
        FolderItem,
        FolderTypeItem,
    )


FOLDERS_MODEL_SENDER_NAME = "qt_folders_model"
FOLDER_ID_ROLE = QtCore.Qt.UserRole + 1
FOLDER_NAME_ROLE = QtCore.Qt.UserRole + 2
FOLDER_PATH_ROLE = QtCore.Qt.UserRole + 3
FOLDER_TYPE_ROLE = QtCore.Qt.UserRole + 4
FOLDER_PATH_FILTER_ROLE = QtCore.Qt.UserRole + 6
FOLDER_STATUS_ROLE = QtCore.Qt.UserRole + 7
FOLDER_STATUS_ICON_ROLE = QtCore.Qt.UserRole + 8


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
    item: QtGui.QStandardItem
    parent_id: str | None
    name: str
    path: str
    label: str
    folder_type: str
    status: str
    path_filter: str

    @classmethod
    def from_folder_item(
        cls,
        item: QtGui.QStandardItem,
        folder_item: FolderItem,
        label_path: str,
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


class RefreshTask(QtCore.QObject, QtCore.QRunnable):
    finished = QtCore.Signal(str, bool)

    def __init__(
        self,
        refresh_task_id: str,
        default_output: Any,
        func: Callable,
        *args,
        **kwargs,
    ):
        QtCore.QObject.__init__(self)
        QtCore.QRunnable.__init__(self)

        self.id = refresh_task_id
        self.started = False
        self._callback = partial(func, *args, **kwargs)
        self._exception = None
        self._traceback = None
        self._result = default_output

    def is_failed(self) -> bool:
        return self._exception is not None

    def get_result(self):
        return self._result

    def print_traceback(self):
        if self._traceback:
            print(self._traceback)

    def run(self) -> None:
        self.started = True
        success = False
        try:
            self._result = self._callback()

            success = True
        except Exception as exc:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err_traceback = "".join(traceback.format_exception(
                exc_type, exc_value, exc_traceback
            ))
            self._traceback = err_traceback
            self._exception = exc

        finally:
            self.finished.emit(self.id, success)


class FoldersQtModel(QtGui.QStandardItemModel):
    """Folders model which cares about refresh of folders.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        The model contains both **Folders** and **Status** columns.
        Visibility of the status column is controlled by the view.
    """
    _default_folder_icon = None
    refreshed = QtCore.Signal()

    def __init__(self, controller):
        super().__init__()
        refresh_threadpool = QtCore.QThreadPool()
        refresh_threadpool.setMaxThreadCount(2)

        self.setColumnCount(2)
        self.setHeaderData(0, QtCore.Qt.Horizontal, "Folders")
        self.setHeaderData(1, QtCore.Qt.Horizontal, "")

        self._controller = controller
        self._fill_data = _FillData()

        self._refresh_threadpool = refresh_threadpool
        self._refresh_tasks = {}
        self._current_refresh_task = None
        self._last_project_name = None
        self._current_refresh_thread = None

        self._has_content = False
        self._is_refreshing = False

    @property
    def is_refreshing(self):
        """Model is refreshing.

        Returns:
            bool: True if model is refreshing.
        """
        return self._is_refreshing

    @property
    def has_content(self):
        """Has at least one folder.

        Returns:
            bool: True if model has at least one folder.
        """

        return self._has_content

    def refresh(self):
        """Refresh folders for last selected project.

        Force to update folders model from controller. This may or may not
        trigger query from server, that's based on controller's cache.
        """

        self.set_project_name(self._last_project_name)

    def get_index_by_id(self, item_id: str) -> QtCore.QModelIndex:
        """Get index by folder id.

        Returns:
            QModelIndex: Index of the folder. Can be invalid if folder
                is not available.
        """
        fill_item = self._fill_data.items_by_id.get(item_id)
        if fill_item is None:
            return QtCore.QModelIndex()
        return self.indexFromItem(fill_item.item)

    def get_item_id_by_path(self, folder_path):
        """Get folder id by path.

        Args:
            folder_path (str): Folder path.

        Returns:
            Union[str, None]: Folder id or None if folder is not available.

        """
        for folder_id, item in self._fill_data.items_by_id.items():
            if item.path == folder_path:
                return folder_id
        return None

    def get_project_name(self) -> str | None:
        """Project name which model currently use.

        Returns:
            str | None: Currently used project name.

        """
        return self._last_project_name

    def set_project_name(self, project_name: str | None) -> None:
        """Refresh folders items.

        Refresh start thread because it can cause that controller can
        start query from database if folders are not cached.
        """

        if not project_name:
            self._last_project_name = project_name
            self._fill_items(
                project_name, {}, [], []
            )
            self._current_refresh_task = None
            return

        self._is_refreshing = True

        if self._last_project_name != project_name:
            self._clear_items()
        self._last_project_name = project_name

        refresh_task = self._refresh_tasks.get(project_name)
        if refresh_task is not None:
            self._current_refresh_task = refresh_task
            return

        refresh_task = RefreshTask(
            project_name,
            ({}, []),
            self._thread_getter,
            project_name,
        )

        self._current_refresh_task = refresh_task
        self._refresh_tasks[refresh_task.id] = refresh_task
        refresh_task.finished.connect(self._on_refresh_task)
        self._refresh_threadpool.start(refresh_task)
        # NOTE: The `msleep` was added to fix workfiles tool refresh in
        #   3ds Max 2027. It looks like there must be one more line running
        #   code after the start of the thread task. Otherwise, the thread
        #   would not be started but will trigger 'finished' signal directly.
        QtCore.QThread.msleep(5)

    @classmethod
    def _get_default_folder_icon(cls):
        if cls._default_folder_icon is None:
            cls._default_folder_icon = get_qt_icon(
                AwesomeFontIcon(
                    "fa.folder",
                    color=get_default_entity_icon_color(),
                )
            )
        return cls._default_folder_icon

    def _clear_items(self) -> None:
        self._fill_data = _FillData()
        self._has_content = False
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

    def _thread_getter(
        self, project_name: str
    ) -> FetchData:
        folder_items = self._controller.get_folder_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        folder_type_items = []
        if hasattr(self._controller, "get_folder_type_items"):
            folder_type_items = self._controller.get_folder_type_items(
                project_name, FOLDERS_MODEL_SENDER_NAME
            )

        status_items = []
        if hasattr(self._controller, "get_project_status_items"):
            status_items = self._controller.get_project_status_items(
                project_name, sender=FOLDERS_MODEL_SENDER_NAME
            )
        return FetchData(
            project_name=project_name,
            folder_items_by_id=folder_items,
            folder_type_items=folder_type_items,
            status_items=status_items,
        )

    def _on_refresh_task(self, refresh_task_id: str, success: bool):
        """Callback when refresh thread is finished.

        Technically can be running multiple refresh threads at the same time,
        to avoid using values from wrong thread, we check if thread id is
        current refresh thread id.

        Folders are stored by id.

        Args:
            refresh_task_id (str): Thread id.
            success (bool): True if refresh was successful.

        """
        # Make sure to remove thread from '_refresh_threads' dict
        refresh_task = self._refresh_tasks.pop(refresh_task_id)
        refresh_task.print_traceback()
        if (
            self._current_refresh_task is None
            or refresh_task_id != self._current_refresh_task.id
        ):
            return

        # TODO visualize that refresh failed
        # if not success:
        #     pass

        result = refresh_task.get_result()

        self._fill_items(
            result.project_name,
            result.folder_items_by_id,
            result.folder_type_items,
            result.status_items,
        )
        self._current_refresh_task = None

    def _get_folder_item_icon(
        self,
        folder_type: str,
        folder_type_icons_by_name: dict[str, QtGui.QIcon | None],
    ) -> QtGui.QIcon:
        icon = folder_type_icons_by_name.get(folder_type)
        if icon is None:
            icon = get_qt_icon(MaterialSymbolsIcon(
                "folder", get_default_entity_icon_color(),
            ))
            folder_type_icons_by_name[folder_type] = icon
        return icon

    def _fill_item_data(
        self,
        item: QtGui.QStandardItem,
        folder_item: FolderItem,
        folder_type_icons_by_name: dict[str, QtGui.QIcon | None],
        status_icon_by_name: dict[str, QtGui.QIcon | None],
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
        item.setData(folder_item.label, QtCore.Qt.DisplayRole)
        item.setData(icon, QtCore.Qt.DecorationRole)
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
        folder_type_icons_by_name: dict[str, QtGui.QIcon | None],
        status_icon_by_name: dict[str, QtGui.QIcon | None],
    ) -> None:
        """

        Args:
            statuses_changed (bool): Whether the statuses have changed.
            folder_types_changed (bool): Whether the folder types have changed.
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
            item.setData(icon, QtCore.Qt.DecorationRole)

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
                QtCore.Qt.DisplayRole
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
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        role: int = QtCore.Qt.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None

        if index.column() != 0:
            return self._get_index_data(index, role)

        return super().data(index, role)

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
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
        if role == QtCore.Qt.DecorationRole:
            role = FOLDER_STATUS_ICON_ROLE
        elif role == QtCore.Qt.ToolTipRole:
            role = FOLDER_STATUS_ROLE
        elif role < QtCore.Qt.UserRole:
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
            self._is_refreshing = False
            return

        self._has_content = True
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

        self._is_refreshing = False
        self.refreshed.emit()

    def _fill_from_scratch(
        self,
        fill_data: _FillData,
        folder_items_by_id: dict[str, FolderItem],
        folder_type_icons_by_name: dict[str, QtGui.QIcon | None],
        status_icon_by_name: dict[str, QtGui.QIcon | None],
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
                item = QtGui.QStandardItem()
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
        folder_type_icons_by_name: dict[str, QtGui.QIcon | None],
        status_icon_by_name: dict[str, QtGui.QIcon | None],
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
                    item = QtGui.QStandardItem()
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


class FoldersProxyModel(RecursiveSortFilterProxyModel):
    def __init__(self):
        super().__init__()

        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

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

    def set_folder_ids_filter(self, folder_ids: Optional[list[str]]):
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


class FoldersWidget(QtWidgets.QWidget):
    """Folders widget.

    Widget that handles folders view, model and selection.

    Expected selection handling is disabled by default. If enabled, the
    widget will handle the expected in predefined way. Widget is listening
    to event 'expected_selection_changed' with expected event data below,
    the same data must be available when called method
    'get_expected_selection_data' on controller.

    {
        "folder": {
            "current": bool,               # Folder is what should be set now
            "folder_id": Union[str, None], # Folder id that should be selected
        },
        ...
    }

    Selection is confirmed by calling method 'expected_folder_selected' on
    controller.


    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        parent (QtWidgets.QWidget): The parent widget.
        handle_expected_selection (bool): If True, the widget will handle
            the expected selection. Defaults to False.
    """

    double_clicked = QtCore.Signal(QtGui.QMouseEvent)
    selection_changed = QtCore.Signal()
    refreshed = QtCore.Signal()

    def __init__(
        self,
        controller,
        parent,
        handle_expected_selection=False,
    ):
        super().__init__(parent)

        folders_view = AYTreeView(self)
        folders_view.setSelectionMode(AYTreeView.SelectionMode.SingleSelection)

        folders_model = FoldersQtModel(controller)
        folders_proxy_model = FoldersProxyModel()
        folders_proxy_model.setSourceModel(folders_model)
        folders_proxy_model.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

        folders_view.setModel(folders_proxy_model)

        header = folders_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(1, 30)
        folders_view.setColumnHidden(1, True)
        folders_view.setItemDelegateForColumn(
            1,
            CenteredIconDelegate(
                parent=folders_view,
                style_model=get_ayon_style().model,
                variant=QTreeViewVariants.Default.value,
            )
        )

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(folders_view, 1)

        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_selection_change,
        )
        controller.register_event_callback(
            "folders.refresh.finished",
            self._on_folders_refresh_finished
        )
        controller.register_event_callback(
            "controller.refresh.finished",
            self._on_controller_refresh
        )
        controller.register_event_callback(
            "expected_selection_changed",
            self._on_expected_selection_change
        )

        selection_model = folders_view.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_change)
        folders_view.double_clicked.connect(self.double_clicked)
        folders_model.refreshed.connect(self._on_model_refresh)

        self._controller = controller
        self._folders_view = folders_view
        self._folders_model = folders_model
        self._folders_proxy_model = folders_proxy_model

        self._handle_expected_selection = handle_expected_selection
        self._expected_selection = None

    @property
    def is_refreshing(self):
        """Model is refreshing.

        Returns:
            bool: True if model is refreshing.
        """

        return self._folders_model.is_refreshing

    @property
    def has_content(self):
        """Has at least one folder.

        Returns:
            bool: True if model has at least one folder.
        """

        return self._folders_model.has_content

    def set_name_filter(self, name):
        """Set filter of folder name.

        Args:
            name (str): The string filter.
        """

        self._folders_proxy_model.set_name_filter(name)
        if name:
            self._folders_view.expandAll()

    def set_folder_ids_filter(self, folder_ids: Optional[list[str]]):
        """Set filter of folder ids.

        Args:
            folder_ids (list[str]): The list of folder ids.

        """
        self._folders_proxy_model.set_folder_ids_filter(folder_ids)

    def set_header_visible(self, visible: bool):
        self._folders_view.setHeaderHidden(not visible)

    def set_status_column_visible(self, visible: bool):
        self._folders_view.setColumnHidden(1, not visible)

    def refresh(self):
        """Refresh folders model.

        Force to update folders model from controller.
        """

        self._folders_model.refresh()

    def get_project_name(self):
        """Project name in which folders widget currently is.

        Returns:
            Union[str, None]: Currently used project name.
        """

        return self._folders_model.get_project_name()

    def set_project_name(self, project_name):
        """Set project name.

        Do not use this method when controller is handling selection of
        project using 'selection.project.changed' event.

        Args:
            project_name (str): Project name.
        """

        self._folders_model.set_project_name(project_name)

    def get_selected_folder_id(self):
        """Get selected folder id.

        Returns:
            Union[str, None]: Folder id which is selected.
        """

        return self._get_selected_item_id()

    def get_selected_folder_path(self):
        """Get selected folder id.

        Returns:
            Union[str, None]: Folder path which is selected.
        """

        return self._get_selected_item_value(FOLDER_PATH_ROLE)

    def get_selected_folder_label(self):
        """Selected folder label.

        Returns:
            Union[str, None]: Selected folder label.
        """

        item_id = self._get_selected_item_id()
        return self.get_folder_label(item_id)

    def get_folder_label(self, folder_id):
        """Folder label for a given folder id.

        Returns:
            Union[str, None]: Folder label.
        """

        index = self._folders_model.get_index_by_id(folder_id)
        if index.isValid():
            return index.data(QtCore.Qt.DisplayRole)
        return None

    def set_selected_folder(self, folder_id):
        """Change selection.

        Args:
            folder_id (Union[str, None]): Folder id or None to deselect.

        Returns:
            bool: Requested folder was selected.
        """
        if folder_id is None:
            self._folders_view.clearSelection()
            return True

        if folder_id == self._get_selected_item_id():
            return True
        index = self._folders_model.get_index_by_id(folder_id)
        if not index.isValid():
            return False

        proxy_index = self._folders_proxy_model.mapFromSource(index)
        if not proxy_index.isValid():
            return False

        selection_model = self._folders_view.selectionModel()
        selection_model.setCurrentIndex(
            proxy_index,
            QtCore.QItemSelectionModel.ClearAndSelect
            | QtCore.QItemSelectionModel.Rows
        )
        return True

    def set_selected_folder_path(self, folder_path):
        """Set selected folder by path.

        Args:
            folder_path (str): Folder path.

        Returns:
            bool: Requested folder was selected.

        """
        if folder_path is None:
            self._folders_view.clearSelection()
            return True

        folder_id = self._folders_model.get_item_id_by_path(folder_path)
        if folder_id is None:
            return False
        return self.set_selected_folder(folder_id)

    def set_deselectable(self, enabled):
        """Set deselectable mode.

        Items in view can be deselected.

        Args:
            enabled (bool): Enable deselectable mode.
        """

        self._folders_view.set_deselectable(enabled)

    def _get_selected_index(self):
        return self._folders_model.get_index_by_id(
            self.get_selected_folder_id()
        )

    def _on_project_selection_change(self, event):
        project_name = event["project_name"]
        self.set_project_name(project_name)

    def _on_folders_refresh_finished(self, event):
        if event["sender"] != FOLDERS_MODEL_SENDER_NAME:
            self.set_project_name(event["project_name"])

    def _on_controller_refresh(self):
        self._update_expected_selection()

    def _on_model_refresh(self):
        if self._expected_selection:
            self._set_expected_selection()
        self._folders_proxy_model.sort(0)
        self.refreshed.emit()

    def _get_selected_item_id(self):
        return self._get_selected_item_value(FOLDER_ID_ROLE)

    def _get_selected_item_value(self, role):
        selection_model = self._folders_view.selectionModel()
        for index in selection_model.selectedRows():
            item_id = index.data(role)
            if item_id is not None:
                return item_id
        return None

    def _on_selection_change(self):
        item_id = self._get_selected_item_id()
        self._controller.set_selected_folder(item_id)
        self.selection_changed.emit()

    # Expected selection handling
    def _on_expected_selection_change(self, event):
        self._update_expected_selection(event.data)

    def _update_expected_selection(self, expected_data=None):
        if not self._handle_expected_selection:
            return

        if expected_data is None:
            expected_data = self._controller.get_expected_selection_data()

        folder_data = expected_data.get("folder")
        if not folder_data or not folder_data["current"]:
            return

        folder_id = folder_data["id"]
        self._expected_selection = folder_id
        if not self._folders_model.is_refreshing:
            self._set_expected_selection()

    def _set_expected_selection(self):
        if not self._handle_expected_selection:
            return

        folder_id = self._expected_selection
        self._expected_selection = None
        if folder_id is not None:
            self.set_selected_folder(folder_id)
        self._controller.expected_folder_selected(folder_id)


class SimpleSelectionModel(object):
    """Model handling selection changes.

    Triggering events:
    - "selection.project.changed"
    - "selection.folder.changed"
    """

    event_source = "selection.model"

    def __init__(self, controller):
        self._controller = controller

        self._project_name = None
        self._folder_id = None
        self._task_id = None
        self._task_name = None

    def get_selected_project_name(self):
        return self._project_name

    def set_selected_project(self, project_name):
        self._project_name = project_name
        self._controller.emit_event(
            "selection.project.changed",
            {"project_name": project_name},
            self.event_source
        )

    def get_selected_folder_id(self):
        return self._folder_id

    def set_selected_folder(self, folder_id):
        if folder_id == self._folder_id:
            return
        self._folder_id = folder_id
        self._controller.emit_event(
            "selection.folder.changed",
            {
                "project_name": self._project_name,
                "folder_id": folder_id,
            },
            self.event_source
        )


class SimpleFoldersController(object):
    def __init__(self):
        self._event_system = self._create_event_system()
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._selection_model = SimpleSelectionModel(self)
        self._expected_selection = HierarchyExpectedSelection(
            self, handle_project=False, handle_folder=True, handle_task=False
        )

    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    # Model functions
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)

    def get_expected_selection_data(self):
        self._expected_selection.get_expected_selection_data()

    def expected_folder_selected(self, folder_id):
        self._expected_selection.expected_folder_selected(folder_id)

    def _create_event_system(self):
        return QueuedEventSystem()


class SimpleFoldersWidget(FoldersWidget):
    def __init__(self, controller=None, *args, **kwargs):
        if controller is None:
            controller = SimpleFoldersController()
        super(SimpleFoldersWidget, self).__init__(controller, *args, **kwargs)

    def set_project_name(self, project_name):
        self._controller.set_selected_project(project_name)
        super(SimpleFoldersWidget, self).set_project_name(project_name)

    def _on_project_selection_change(self, event):
        """Ignore project selection change from controller.

        Only who can trigger project change is this widget with
            'set_project_name' which already cares about project change.

        Args:
            event (Event): Triggered event.
        """
        pass


class FoldersFiltersWidget(QtWidgets.QWidget):
    """Helper widget for most commonly used filters in context selection."""
    text_changed = QtCore.Signal(str)
    my_tasks_changed = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        # TODO: fix the focus/unfoucs text color when click out of window
        # text changing to black which looking odd fix this at all AYLineEdit
        folders_filter_input = AYLineEdit(
            placeholder="Folder name filter...",
            variant=AYLineEdit.Variants.Search_Field,
            parent=self,
        )

        my_tasks_checkbox = AYButton(
            icon="assignment_ind",
            checkable=True,
            tooltip="Only show folders that have a task assigned to you.",
            parent=parent,
        )
        my_tasks_checkbox.setChecked(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(folders_filter_input, 1)
        layout.addWidget(my_tasks_checkbox, 0)

        folders_filter_input.textChanged.connect(self.text_changed)
        my_tasks_checkbox.toggled.connect(self.my_tasks_changed)

        self._folders_filter_input = folders_filter_input
        self._my_tasks_checkbox = my_tasks_checkbox

    def is_my_tasks_checked(self) -> bool:
        return self._my_tasks_checkbox.isChecked()

    def text(self) -> str:
        return self._folders_filter_input.text()

    def set_text(self, text: str) -> None:
        self._folders_filter_input.setText(text)

    def set_my_tasks_checked(self, checked: bool) -> None:
        self._my_tasks_checkbox.setChecked(checked)

    def _on_my_tasks_change(self, state: bool) -> None:
        self.my_tasks_changed.emit(state)
