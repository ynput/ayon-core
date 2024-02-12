from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils.views import DeselectableTreeView
from ayon_core.tools.utils.lib import get_default_task_icon

TASK_NAME_ROLE = QtCore.Qt.UserRole + 1
TASK_TYPE_ROLE = QtCore.Qt.UserRole + 2
TASK_ORDER_ROLE = QtCore.Qt.UserRole + 3


class TasksModel(QtGui.QStandardItemModel):
    """Tasks model.

    Task model must have set context of asset documents.

    Items in model are based on 0-infinite asset documents. Always contain
    an interserction of context asset tasks. When no assets are in context
    them model is empty if 2 or more are in context assets that don't have
    tasks with same names then model is empty too.

    Args:
        controller (PublisherController): Controller which handles creation and
            publishing.
    """
    def __init__(self, controller, allow_empty_task=False):
        super(TasksModel, self).__init__()

        self._allow_empty_task = allow_empty_task
        self._controller = controller
        self._items_by_name = {}
        self._asset_names = []
        self._task_names_by_asset_name = {}

    def set_asset_names(self, asset_names):
        """Set assets context."""
        self._asset_names = asset_names
        self.reset()

    @staticmethod
    def get_intersection_of_tasks(task_names_by_asset_name):
        """Calculate intersection of task names from passed data.

        Example:
        ```
        # Passed `task_names_by_asset_name`
        {
            "asset_1": ["compositing", "animation"],
            "asset_2": ["compositing", "editorial"]
        }
        ```
        Result:
        ```
        # Set
        {"compositing"}
        ```

        Args:
            task_names_by_asset_name (dict): Task names in iterable by parent.
        """
        tasks = None
        for task_names in task_names_by_asset_name.values():
            if tasks is None:
                tasks = set(task_names)
            else:
                tasks &= set(task_names)

            if not tasks:
                break
        return tasks or set()

    def is_task_name_valid(self, asset_name, task_name):
        """Is task name available for asset.

        Args:
            asset_name (str): Name of asset where should look for task.
            task_name (str): Name of task which should be available in asset's
                tasks.
        """
        if asset_name not in self._task_names_by_asset_name:
            return False

        if self._allow_empty_task and not task_name:
            return True

        task_names = self._task_names_by_asset_name[asset_name]
        if task_name in task_names:
            return True
        return False

    def reset(self):
        """Update model by current context."""
        if not self._asset_names:
            self._items_by_name = {}
            self._task_names_by_asset_name = {}
            self.clear()
            return

        task_names_by_asset_name = (
            self._controller.get_task_names_by_asset_names(self._asset_names)
        )

        self._task_names_by_asset_name = task_names_by_asset_name

        new_task_names = self.get_intersection_of_tasks(
            task_names_by_asset_name
        )
        if self._allow_empty_task:
            new_task_names.add("")
        old_task_names = set(self._items_by_name.keys())
        if new_task_names == old_task_names:
            return

        root_item = self.invisibleRootItem()
        for task_name in old_task_names:
            if task_name not in new_task_names:
                item = self._items_by_name.pop(task_name)
                root_item.removeRow(item.row())

        new_items = []
        for task_name in new_task_names:
            if task_name in self._items_by_name:
                continue

            item = QtGui.QStandardItem(task_name)
            item.setData(task_name, TASK_NAME_ROLE)
            if task_name:
                item.setData(get_default_task_icon(), QtCore.Qt.DecorationRole)
            self._items_by_name[task_name] = item
            new_items.append(item)

        if new_items:
            root_item.appendRows(new_items)

    def headerData(self, section, orientation, role=None):
        if role is None:
            role = QtCore.Qt.EditRole
        # Show nice labels in the header
        if section == 0:
            if (
                role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole)
                and orientation == QtCore.Qt.Horizontal
            ):
                return "Tasks"

        return super(TasksModel, self).headerData(section, orientation, role)


class TasksProxyModel(QtCore.QSortFilterProxyModel):
    def lessThan(self, x_index, y_index):
        x_order = x_index.data(TASK_ORDER_ROLE)
        y_order = y_index.data(TASK_ORDER_ROLE)
        if x_order is not None and y_order is not None:
            if x_order < y_order:
                return True
            if x_order > y_order:
                return False

        elif x_order is None and y_order is not None:
            return True

        elif y_order is None and x_order is not None:
            return False

        x_name = x_index.data(QtCore.Qt.DisplayRole)
        y_name = y_index.data(QtCore.Qt.DisplayRole)
        if x_name == y_name:
            return True

        if x_name == tuple(sorted((x_name, y_name)))[0]:
            return True
        return False


class CreateWidgetTasksWidget(QtWidgets.QWidget):
    """Widget showing active Tasks

    Deprecated:
        This widget will be removed soon. Please do not use it in new code.
    """

    task_changed = QtCore.Signal()

    def __init__(self, controller, parent):
        self._controller = controller

        self._enabled = None

        super(CreateWidgetTasksWidget, self).__init__(parent)

        tasks_view = DeselectableTreeView(self)
        tasks_view.setIndentation(0)
        tasks_view.setSortingEnabled(True)
        tasks_view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        header_view = tasks_view.header()
        header_view.setSortIndicator(0, QtCore.Qt.AscendingOrder)

        tasks_model = TasksModel(self._controller)
        tasks_proxy = TasksProxyModel()
        tasks_proxy.setSourceModel(tasks_model)
        tasks_view.setModel(tasks_proxy)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tasks_view)

        selection_model = tasks_view.selectionModel()
        selection_model.selectionChanged.connect(self._on_task_change)

        self._tasks_model = tasks_model
        self._tasks_proxy = tasks_proxy
        self._tasks_view = tasks_view

        self._last_selected_task_name = None

    def refresh(self):
        self._tasks_model.refresh()

    def set_asset_id(self, asset_id):
        # Try and preserve the last selected task and reselect it
        # after switching assets. If there's no currently selected
        # asset keep whatever the "last selected" was prior to it.
        current = self.get_selected_task_name()
        if current:
            self._last_selected_task_name = current

        self._tasks_model.set_asset_id(asset_id)

        if self._last_selected_task_name:
            self.select_task_name(self._last_selected_task_name)

        # Force a task changed emit.
        self.task_changed.emit()

    def _clear_selection(self):
        selection_model = self._tasks_view.selectionModel()
        selection_model.clearSelection()

    def select_task_name(self, task_name):
        """Select a task by name.

        If the task does not exist in the current model then selection is only
        cleared.

        Args:
            task_name (str): Name of the task to select.

        """
        task_view_model = self._tasks_view.model()
        if not task_view_model:
            return

        # Clear selection
        selection_model = self._tasks_view.selectionModel()
        selection_model.clearSelection()

        # Select the task
        mode = (
            QtCore.QItemSelectionModel.Select
            | QtCore.QItemSelectionModel.Rows
        )
        for row in range(task_view_model.rowCount()):
            index = task_view_model.index(row, 0)
            name = index.data(TASK_NAME_ROLE)
            if name == task_name:
                selection_model.select(index, mode)

                # Set the currently active index
                self._tasks_view.setCurrentIndex(index)
                break

        last_selected_task_name = self.get_selected_task_name()
        if last_selected_task_name:
            self._last_selected_task_name = last_selected_task_name

        if not self._enabled:
            current = self.get_selected_task_name()
            if current:
                self._last_selected_task_name = current
            self._clear_selection()

    def get_selected_task_name(self):
        """Return name of task at current index (selected)

        Returns:
            str: Name of the current task.

        """
        index = self._tasks_view.currentIndex()
        selection_model = self._tasks_view.selectionModel()
        if index.isValid() and selection_model.isSelected(index):
            return index.data(TASK_NAME_ROLE)
        return None

    def get_selected_task_type(self):
        index = self._tasks_view.currentIndex()
        selection_model = self._tasks_view.selectionModel()
        if index.isValid() and selection_model.isSelected(index):
            return index.data(TASK_TYPE_ROLE)
        return None

    def set_asset_name(self, asset_name):
        current = self.get_selected_task_name()
        if current:
            self._last_selected_task_name = current

        self._tasks_model.set_asset_names([asset_name])
        if self._last_selected_task_name and self._enabled:
            self.select_task_name(self._last_selected_task_name)

        # Force a task changed emit.
        self.task_changed.emit()

    def set_enabled(self, enabled):
        self._enabled = enabled
        if not enabled:
            last_selected_task_name = self.get_selected_task_name()
            if last_selected_task_name:
                self._last_selected_task_name = last_selected_task_name
            self._clear_selection()

        elif self._last_selected_task_name is not None:
            self.select_task_name(self._last_selected_task_name)

    def _on_task_change(self):
        self.task_changed.emit()
