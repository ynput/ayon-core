from __future__ import annotations

import typing

from qtpy import QtCore, QtGui

from ayon_core.lib.icon_definitions import (
    MaterialSymbolsIcon,
    AwesomeFontIcon,
)
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend

if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models import TaskTypeItem, TaskItem


TASK_NAME_ROLE = QtCore.Qt.UserRole + 1
TASK_TYPE_ROLE = QtCore.Qt.UserRole + 2
TASK_ORDER_ROLE = QtCore.Qt.UserRole + 3


class TasksModel(QtGui.QStandardItemModel):
    """Tasks model.

    Task model must have set context of folder paths.

    Items in model are based on 0-infinite folders. Always contain
    an interserction of context folder tasks. When no folders are in context
    them model is empty if 2 or more are in context folders that don't have
    tasks with same names then model is empty too.

    Args:
        controller (AbstractPublisherFrontend): Controller which handles
            creation and publishing.

    """
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        allow_empty_task: bool = False
    ) -> None:
        super().__init__()

        self._allow_empty_task: bool = allow_empty_task
        self._controller: AbstractPublisherFrontend = controller
        self._items_by_name: dict[str, QtGui.QStandardItem] = {}
        self._folder_paths: set[str] = set()
        self._task_names_by_folder_path: dict[str, set[str]] = {}
        self._promised_task_lists: list[list[str]] = []

    def set_folder_paths(
        self,
        folder_paths: set[str],
        promised_task_lists: list[list[str]] | None = None,
    ) -> None:
        """Set folder paths and optional promised tasks."""
        self._folder_paths = folder_paths
        self._promised_task_lists = promised_task_lists or []
        self.reset()

    @staticmethod
    def get_intersection_of_tasks(
        task_names_by_folder_path: dict[str, set[str]]
    ) -> set[str]:
        """Calculate intersection of task names from passed data.

        Example:
        ```
        # Passed `task_names_by_folder_path`
        {
            "/folder_1": {"compositing", "animation"},
            "/folder_2": {"compositing", "editorial"}
        }
        ```
        Result:
        ```
        # Set
        {"compositing"}
        ```

        Args:
            task_names_by_folder_path (dict): Task names in iterable by parent.

        """
        tasks = None
        for task_names in task_names_by_folder_path.values():
            if tasks is None:
                tasks = set(task_names)
            else:
                tasks &= set(task_names)

            if not tasks:
                break

        return tasks or set()

    def is_task_name_valid(
        self, folder_path: str, task_name: str | None
    ) -> bool:
        """Is task name available for folder.

        Todos:
            Move this method to PublisherController.

        Args:
            folder_path (str): Fodler path where should look for task.
            task_name (str | None): Name of task which should be available
                in folder tasks.
        """
        if folder_path not in self._task_names_by_folder_path:
            return False

        if self._allow_empty_task and not task_name:
            return True

        task_names = self._task_names_by_folder_path[folder_path]
        if task_name in task_names:
            return True
        return False

    def reset(self) -> None:
        """Update model by current context."""
        if not self._folder_paths and not self._promised_task_lists:
            self._items_by_name = {}
            self._task_names_by_folder_path = {}
            root_item = self.invisibleRootItem()
            root_item.removeRows(0, self.rowCount())
            return

        task_items_by_folder_path: dict[str, list[TaskItem]] = (
            self._controller.get_task_items_by_folder_paths(
                self._folder_paths
            )
        )

        task_names_by_folder_path: dict[str, set[str]] = {
            folder_path: {item.name for item in task_items}
            for folder_path, task_items in task_items_by_folder_path.items()
        }
        self._task_names_by_folder_path = task_names_by_folder_path

        new_task_names = None
        if self._folder_paths:
            new_task_names = self.get_intersection_of_tasks(
                task_names_by_folder_path
            )
            if self._allow_empty_task:
                new_task_names.add("")

        for promised_tasks in self._promised_task_lists:
            promised_tasks = set(promised_tasks)
            if new_task_names is None:
                new_task_names = promised_tasks
            else:
                new_task_names &= promised_tasks

        old_task_names = set(self._items_by_name.keys())
        if new_task_names == old_task_names:
            return

        root_item = self.invisibleRootItem()
        for task_name in old_task_names:
            if task_name not in new_task_names:
                item = self._items_by_name.pop(task_name)
                root_item.removeRow(item.row())

        default_icon = get_qt_icon(AwesomeFontIcon(
            "fa.male",
            color=get_default_entity_icon_color(),
        ))
        new_items = []
        task_type_items = {
            task_type_item.name: task_type_item
            for task_type_item in self._controller.get_task_type_items(
                self._controller.get_current_project_name()
            )
        }
        type_item_by_task_name: dict[str, TaskTypeItem] = {}
        for task_items in task_items_by_folder_path.values():
            for task_item in task_items:
                task_name = task_item.name
                if (
                    task_name not in new_task_names
                    or task_name in type_item_by_task_name
                ):
                    continue
                task_type_name = task_item.task_type
                task_type_item = task_type_items.get(task_type_name)
                if task_type_item:
                    type_item_by_task_name[task_name] = task_type_item

        for task_name in new_task_names:
            item = self._items_by_name.get(task_name)
            if item is None:
                item = QtGui.QStandardItem(task_name)
                item.setData(task_name, TASK_NAME_ROLE)
                self._items_by_name[task_name] = item
                new_items.append(item)

            if not task_name:
                continue

            task_type_item: TaskTypeItem | None = type_item_by_task_name.get(
                task_name
            )
            icon_name = icon_color = None
            if task_type_item is not None:
                icon_name = task_type_item.icon
                icon_color = task_type_item.color

            icon = None
            if icon_name:
                if not icon_color:
                    icon_color = get_default_entity_icon_color()
                icon = get_qt_icon(
                    MaterialSymbolsIcon(icon_name, color=icon_color)
                )
            if icon is None:
                icon = default_icon
            item.setData(icon, QtCore.Qt.DecorationRole)

        if new_items:
            root_item.appendRows(new_items)
