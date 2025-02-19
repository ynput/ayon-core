import collections
import hashlib

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import (
    RecursiveSortFilterProxyModel,
    DeselectableTreeView,
    TasksQtModel,
    TASKS_MODEL_SENDER_NAME,
)
from ayon_core.tools.utils.tasks_widget import (
    ITEM_ID_ROLE,
    ITEM_NAME_ROLE,
    PARENT_ID_ROLE,
    TASK_TYPE_ROLE,
)
from ayon_core.tools.utils.lib import RefreshThread

# Role that can't clash with default 'tasks_widget' roles
FOLDER_LABEL_ROLE = QtCore.Qt.UserRole + 100


class LoaderTasksQtModel(TasksQtModel):
    column_labels = [
        "Task name",
        "Task type",
        "Folder"
    ]

    def __init__(self, controller):
        super().__init__(controller)

        self.setColumnCount(len(self.column_labels))
        for idx, label in enumerate(self.column_labels):
            self.setHeaderData(idx, QtCore.Qt.Horizontal, label)

        self._items_by_id = {}
        self._groups_by_name = {}
        self._last_folder_ids = set()

    def refresh(self):
        """Refresh tasks for selected folders."""

        self._refresh(self._last_project_name, self._last_folder_ids)

    def set_context(self, project_name, folder_ids):
        self._refresh(project_name, folder_ids)

    # Mark some functions from 'TasksQtModel' as not implemented
    def get_index_by_name(self, task_name):
        raise NotImplementedError(
            "Method 'get_index_by_name' is not implemented."
        )

    def get_last_folder_id(self):
        raise NotImplementedError(
            "Method 'get_last_folder_id' is not implemented."
        )

    def flags(self, _index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def _refresh(self, project_name, folder_ids):
        self._is_refreshing = True
        self._last_project_name = project_name
        self._last_folder_ids = folder_ids
        if not folder_ids:
            self._add_invalid_selection_item()
            self._current_refresh_thread = None
            self._is_refreshing = False
            self.refreshed.emit()
            return

        thread_id = hashlib.sha256(
            "|".join(sorted(folder_ids)).encode()
        ).hexdigest()
        thread = self._refresh_threads.get(thread_id)
        if thread is not None:
            self._current_refresh_thread = thread
            return
        thread = RefreshThread(
            thread_id,
            self._thread_getter,
            project_name,
            folder_ids
        )
        self._current_refresh_thread = thread
        self._refresh_threads[thread.id] = thread
        thread.refresh_finished.connect(self._on_refresh_thread)
        thread.start()

    def _thread_getter(self, project_name, folder_ids):
        task_items = self._controller.get_task_items(
            project_name, folder_ids, sender=TASKS_MODEL_SENDER_NAME
        )
        task_type_items = {}
        if hasattr(self._controller, "get_task_type_items"):
            task_type_items = self._controller.get_task_type_items(
                project_name, sender=TASKS_MODEL_SENDER_NAME
            )
        folder_ids = {
            task_item.parent_id
            for task_item in task_items
        }
        folder_labels_by_id = self._controller.get_folder_labels(
            project_name, folder_ids
        )
        return task_items, task_type_items, folder_labels_by_id

    def _on_refresh_thread(self, thread_id):
        """Callback when refresh thread is finished.

        Technically can be running multiple refresh threads at the same time,
        to avoid using values from wrong thread, we check if thread id is
        current refresh thread id.

        Tasks are stored by name, so if a folder has same task name as
        previously selected folder it keeps the selection.

        Args:
            thread_id (str): Thread id.
        """

        # Make sure to remove thread from '_refresh_threads' dict
        thread = self._refresh_threads.pop(thread_id)
        if (
            self._current_refresh_thread is None
            or thread_id != self._current_refresh_thread.id
        ):
            return

        self._fill_data_from_thread(thread)

        root_item = self.invisibleRootItem()
        self._has_content = root_item.rowCount() > 0
        self._current_refresh_thread = None
        self._is_refreshing = False
        self.refreshed.emit()

    def _clear_items(self):
        self._items_by_id = {}
        self._groups_by_name = {}
        super()._clear_items()

    def _fill_data_from_thread(self, thread):
        task_items, task_type_items, folder_labels_by_id = thread.get_result()
        # Task items are refreshed
        if task_items is None:
            return

        # No tasks are available on folder
        if not task_items:
            self._add_empty_task_item()
            return
        self._remove_invalid_items()

        task_type_item_by_name = {
            task_type_item.name: task_type_item
            for task_type_item in task_type_items
        }
        task_type_icon_cache = {}
        current_ids = set()
        items_by_name = collections.defaultdict(list)
        for task_item in task_items:
            task_id = task_item.task_id
            current_ids.add(task_id)
            item = self._items_by_id.get(task_id)
            if item is None:
                item = QtGui.QStandardItem()
                item.setColumnCount(self.columnCount())
                item.setEditable(False)
                self._items_by_id[task_id] = item

            icon = self._get_task_item_icon(
                task_item,
                task_type_item_by_name,
                task_type_icon_cache
            )
            name = task_item.name
            folder_id = task_item.parent_id
            folder_label = folder_labels_by_id.get(folder_id)

            item.setData(name, QtCore.Qt.DisplayRole)
            item.setData(name, ITEM_NAME_ROLE)
            item.setData(task_item.id, ITEM_ID_ROLE)
            item.setData(task_item.task_type, TASK_TYPE_ROLE)
            item.setData(folder_id, PARENT_ID_ROLE)
            item.setData(folder_label, FOLDER_LABEL_ROLE)
            item.setData(icon, QtCore.Qt.DecorationRole)

            items_by_name[name].append(item)

        root_item = self.invisibleRootItem()

        for task_id in set(self._items_by_id) - current_ids:
            item = self._items_by_id.pop(task_id)
            parent = item.parent()
            if parent is None:
                parent = root_item
            parent.removeRow(item.row())

        used_group_names = set()
        new_root_items = []
        for name, items in items_by_name.items():
            # Make sure item is not parented
            # - this is laziness to avoid re-parenting items which does
            #   complicate the code with no benefit
            for item in items:
                parent = item.parent()
                # If item is in root then model is not None, and
                #   if parent is set then model is None
                if parent is None and item.model() is None:
                    continue

                if parent is None:
                    # We can skip when task stays un-grouped
                    if len(items) == 1:
                        continue
                    parent = root_item

                parent.takeRow(item.row())

            if len(items) == 1:
                new_root_items.extend(items)
                continue

            used_group_names.add(name)
            group_item = self._groups_by_name.get(name)
            if group_item is None:
                group_item = QtGui.QStandardItem()
                group_item.setData(name, QtCore.Qt.DisplayRole)
                group_item.setEditable(False)
                group_item.setColumnCount(self.columnCount())
                self._groups_by_name[name] = group_item
                new_root_items.append(group_item)

            # Use icon from first item
            first_item_icon = items[0].data(QtCore.Qt.DecorationRole)
            task_ids = [
                item.data(ITEM_ID_ROLE)
                for item in items
            ]

            group_item.setData(first_item_icon, QtCore.Qt.DecorationRole)
            group_item.setData("|".join(task_ids), ITEM_ID_ROLE)

            group_item.appendRows(items)

        for name in set(self._groups_by_name.keys()) - used_group_names:
            group_item = self._groups_by_name.pop(name)
            root_item.removeRow(group_item.row())

        if new_root_items:
            root_item.appendRows(new_root_items)

    def data(self, index, role=None):
        if not index.isValid():
            return None

        if role is None:
            role = QtCore.Qt.DisplayRole

        col = index.column()
        if col != 0:
            index = self.index(index.row(), 0, index.parent())

        if col == 1:
            if role == QtCore.Qt.DisplayRole:
                role = TASK_TYPE_ROLE
            else:
                return None

        if col == 2:
            if role == QtCore.Qt.DisplayRole:
                role = FOLDER_LABEL_ROLE
            else:
                return None

        return super().data(index, role)


class LoaderTasksWidget(QtWidgets.QWidget):
    refreshed = QtCore.Signal()

    def __init__(self, controller, parent):
        super().__init__(parent)

        tasks_view = DeselectableTreeView(self)
        # tasks_view.setHeaderHidden(True)
        tasks_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        tasks_view_header = tasks_view.header()
        tasks_view_header.setStretchLastSection(False)

        tasks_model = LoaderTasksQtModel(controller)
        tasks_proxy_model = RecursiveSortFilterProxyModel()
        tasks_proxy_model.setSourceModel(tasks_model)
        tasks_proxy_model.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

        tasks_view.setModel(tasks_proxy_model)
        # Hide folder column by default
        tasks_view.setColumnHidden(2, True)
        tasks_view_header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(tasks_view, 1)

        controller.register_event_callback(
            "selection.folders.changed",
            self._on_folders_selection_changed,
        )
        controller.register_event_callback(
            "tasks.refresh.finished",
            self._on_tasks_refresh_finished
        )

        selection_model = tasks_view.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_change)

        tasks_model.refreshed.connect(self._on_model_refresh)

        self._controller = controller
        self._tasks_view = tasks_view
        self._tasks_model = tasks_model
        self._tasks_proxy_model = tasks_proxy_model

    def set_name_filter(self, name):
        """Set filter of folder name.

        Args:
            name (str): The string filter.

        """
        self._tasks_proxy_model.setFilterFixedString(name)
        if name:
            self._tasks_view.expandAll()

    def refresh(self):
        self._tasks_model.refresh()

    def _clear(self):
        self._tasks_model.clear()

    def _on_tasks_refresh_finished(self, event):
        if event["sender"] != TASKS_MODEL_SENDER_NAME:
            self._set_project_name(event["project_name"])

    def _on_folders_selection_changed(self, event):
        project_name = event["project_name"]
        folder_ids = event["folder_ids"]
        self._tasks_view.setColumnHidden(2, len(folder_ids) == 1)
        self._tasks_model.set_context(project_name, folder_ids)

    def _on_model_refresh(self):
        self._tasks_proxy_model.sort(0)
        self.refreshed.emit()

    def _get_selected_item_ids(self):
        selection_model = self._tasks_view.selectionModel()
        item_ids = set()
        for index in selection_model.selectedIndexes():
            item_id = index.data(ITEM_ID_ROLE)
            if item_id is None:
                continue
            item_ids |= set(item_id.split("|"))
        return item_ids

    def _on_selection_change(self):
        item_ids = self._get_selected_item_ids()
        self._controller.set_selected_tasks(item_ids)
