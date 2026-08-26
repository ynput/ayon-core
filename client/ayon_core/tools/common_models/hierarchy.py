from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import contextlib
from dataclasses import dataclass
import time
from typing import Any, Generator

import ayon_api

from ayon_core.lib import NestedCacheItem

from .projects import TaskTypeItem

HIERARCHY_MODEL_SENDER = "hierarchy.model"


class AbstractHierarchyController(ABC):
    @abstractmethod
    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] = None,
        source: str | None = None,
    ) -> None:
        pass


@dataclass
class FolderItem:
    """Item representing folder entity on a server.

    Folder can be a child of another folder or a project.

    Attributes:
        folder_id (str): Folder id.
        parent_id (str | None): Parent folder id. If 'None' then project
            is parent.
        name (str): Name of folder.
        path (str): Folder path.
        folder_type (str): Type of folder.
        label (str): Folder label.

    """
    folder_id: str
    parent_id: str | None
    name: str
    path: str
    folder_type: str
    label: str

    @property
    def entity_id(self) -> str:
        """Alias for folder_id."""
        return self.folder_id

    @classmethod
    def from_hierarchy_item(cls, item: dict[str, Any]) -> FolderItem:
        """Creates folder item from hierarchy item.

        Args:
            item (dict[str, Any]): Hierarchy item.

        """
        name = item["name"]
        path_parts = list(item["parents"])
        path_parts.append(name)
        path_parts.insert(0, "")
        path = "/".join(path_parts)
        return FolderItem(
            folder_id=item["id"],
            parent_id=item["parentId"],
            name=name,
            path=path,
            folder_type=item["folderType"],
            label=item["label"] or name,
        )

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> FolderItem:
        name = entity["name"]
        return FolderItem(
            folder_id=entity["id"],
            parent_id=entity["parentId"],
            name=name,
            path=entity["path"],
            folder_type=entity["folderType"],
            label=entity["label"] or name,
        )

    def to_data(self) -> dict[str, str | None]:
        """Converts folder item to data.

        Returns:
            dict[str, str | None]: Folder item data.

        """
        return dict(
            folder_id=self.folder_id,
            parent_id=self.parent_id,
            name=self.name,
            path=self.path,
            folder_type=self.folder_type,
            label=self.label,
        )

    @classmethod
    def from_data(cls, data: dict[str, str | None]) -> FolderItem:
        """Re-creates folder item from data.

        Args:
            data (dict[str, str | None]): Folder item data.

        Returns:
            FolderItem: Folder item.

        """
        return cls(**data)


@dataclass
class TaskItem:
    """Task item representing task entity on a server.

    Task is child of a folder.

    Task item has label that is used for display in UI. The label is by
        default using task name and type.

    Args:
        task_id (str): Task id.
        name (str): Name of task.
        name (str | None): Task label.
        task_type (str): Type of task.
        folder_id (str): Parent folder id.
        tags (list[str]): List of tags assigned to task.
        full_label (str): Full label of task. Is filled automatically.

    """
    task_id: str
    name: str
    label: str
    task_type: str
    task_type_order: int
    folder_id: str
    tags: list[str]
    full_label: str = ""

    def __post_init__(self):
        if not self.full_label:
            self.full_label = f"{self.label} ({self.task_type})"

    @property
    def id(self):
        """Alias for task_id.

        Returns:
            str: Task id.

        """
        return self.task_id

    @property
    def parent_id(self):
        """Alias for folder_id.

        Returns:
            str: Folder id.

        """
        return self.folder_id

    def to_data(self) -> dict[str, Any]:
        """Converts task item to data.

        Returns:
            dict[str, Any]: Task item data.

        """
        return dict(
            task_id=self.task_id,
            name=self.name,
            label=self.label,
            folder_id=self.folder_id,
            task_type=self.task_type,
            task_type_order=self.task_type_order,
            tags=self.tags.copy(),
            full_label=self.full_label,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> TaskItem:
        """Re-create task item from data.

        Args:
            data (dict[str, Any]): Task item data.

        Returns:
            TaskItem: Task item.

        """
        return cls(**data)

    @classmethod
    def from_entity(
        cls, entity: dict[str, Any], task_type_order: int
    ) -> TaskItem:
        """Re-create task item from data.

        Args:
            entity (dict[str, Any]): Task entity.
            task_type_order (int): Task type order.

        Returns:
            TaskItem: Task item.

        """
        return cls(
            task_id=entity["id"],
            name=entity["name"],
            label=entity["label"],
            task_type=entity["type"],
            task_type_order=task_type_order,
            folder_id=entity["folderId"],
            tags=entity["tags"],
        )


class HierarchyModel:
    """Model for project hierarchy items.

    Hierarchy items are folders and tasks. Folders can have as parent another
    folder or project. Tasks can have as parent only folder.
    """
    lifetime = 60  # A minute

    def __init__(self, controller):
        self._tags_by_entity_type = NestedCacheItem(
            levels=1, default_factory=dict, lifetime=self.lifetime)
        self._folders_items = NestedCacheItem(
            levels=1, default_factory=dict, lifetime=self.lifetime)
        self._folders_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._task_items = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)
        self._tasks_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._entity_ids_by_assignee = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._folders_refreshing = set()
        self._tasks_refreshing = set()
        self._controller = controller

    def reset(self) -> None:
        self._tags_by_entity_type.reset()
        self._folders_items.reset()
        self._folders_by_id.reset()

        self._task_items.reset()
        self._tasks_by_id.reset()

        self._entity_ids_by_assignee.reset()

    def refresh_project(self, project_name: str) -> None:
        """Force to refresh folder items for a project.

        Args:
            project_name (str): Name of project to refresh.

        """
        self._refresh_folders_cache(project_name)

    def get_folder_items(
        self, project_name: str, sender: str | None
    ) -> dict[str, FolderItem]:
        """Get folder items by project name.

        The folders are cached per project name. If the cache is not valid
        then the folders are queried from server.

        Args:
            project_name (str): Name of project where to look for folders.
            sender (str | None): Who requested the folder ids.

        Returns:
            dict[str, FolderItem]: Folder items by id.

        """
        if not self._folders_items[project_name].is_valid:
            self._refresh_folders_cache(project_name, sender)
        return self._folders_items[project_name].get_data()

    def get_folder_items_by_id(
        self, project_name: str, folder_ids: set[str] | list[str]
    ) -> dict[str, FolderItem | None]:
        """Get folder items by ids.

        This function will query folders if they are not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_ids (set[str] | list[str]): Folder ids.

        Returns:
            dict[str, FolderItem | None]: Folder items by id.

        """
        if not isinstance(folder_ids, set):
            folder_ids = set(folder_ids)

        if self._folders_items[project_name].is_valid:
            cache_data = self._folders_items[project_name].get_data()
            return {
                folder_id: cache_data.get(folder_id)
                for folder_id in folder_ids
            }

        folders = ayon_api.get_folders(
            project_name,
            folder_ids=folder_ids,
            fields=["id", "name", "label", "parentId", "path", "folderType"]
        )
        # Make sure all folder ids are in output
        output = {folder_id: None for folder_id in folder_ids}
        output.update({
            folder["id"]: FolderItem.from_entity(folder)
            for folder in folders
        })
        return output

    def get_folder_items_by_paths(
        self, project_name: str, folder_paths: set[str] | list[str]
    ) -> dict[str, FolderItem | None]:
        """Get folder items by ids.

        This function will query folders if they are not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_paths (set[str] | list[str]): Folder paths.

        Returns:
            dict[str, FolderItem | None]: Folder items by path.

        """
        if not isinstance(folder_paths, set):
            folder_paths = set(folder_paths)
        output: dict[str, FolderItem | None] = {
            folder_path: None for folder_path in folder_paths
        }
        if not folder_paths:
            return output

        if self._folders_items[project_name].is_valid:
            cache_data = self._folders_items[project_name].get_data()
            for folder_item in cache_data.values():
                if folder_item.path in folder_paths:
                    output[folder_item.path] = folder_item
            return output
        folders = ayon_api.get_folders(
            project_name,
            folder_paths=folder_paths,
            fields=["id", "name", "label", "parentId", "path", "folderType"]
        )
        # Make sure all folder ids are in output
        for folder in folders:
            item = FolderItem.from_entity(folder)
            output[item.path] = item
        return output

    def get_folder_item(
        self, project_name: str, folder_id: str
    ) -> FolderItem | None:
        """Get folder item by id.

        This function will query folder if they is not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_id (str): Folder id.

        Returns:
            FolderItem | None: Folder item.

        """
        items = self.get_folder_items_by_id(
            project_name, {folder_id}
        )
        return items.get(folder_id)

    def get_folder_item_by_path(
        self, project_name: str, folder_path: str
    ) -> FolderItem | None:
        """Get folder item by path.

        This function will query folder if they is not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_path (str): Folder path.

        Returns:
            FolderItem | None: Folder item.

        """
        items = self.get_folder_items_by_paths(
            project_name, {folder_path}
        )
        return items.get(folder_path)

    def get_task_item_by_name(
        self,
        project_name: str,
        folder_id: str,
        task_name: str,
        sender: str | None,
    ) -> TaskItem | None:
        """Get task item by name and folder id.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.
            task_name (str): Task name.
            sender (str | None): Who requested the task item.

        Returns:
            TaskItem | None: Task item found by name and folder id.

        """
        for task_item in self.get_task_items(project_name, folder_id, sender):
            if task_item.name == task_name:
                return task_item
        return None

    def get_task_items(
        self,
        project_name: str | None,
        folder_id: str | None,
        sender: str | None,
    ) -> list[TaskItem]:
        if not project_name or not folder_id:
            return []

        task_cache = self._task_items[project_name][folder_id]
        if not task_cache.is_valid:
            self._refresh_tasks_cache(project_name, folder_id, sender)
        return task_cache.get_data()

    def get_folder_entities(
        self, project_name: str | None, folder_ids: set[str] | list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get folder entities by ids.

        Args:
            project_name (str | None): Project name.
            folder_ids (set[str] | list[str]): Folder ids.

        Returns:
            dict[str, dict[str, Any]]: Folder entities by id.

        """
        output = {}
        if not isinstance(folder_ids, set):
            folder_ids = set(folder_ids)

        if not project_name or not folder_ids:
            return output

        folder_ids_to_query = set()
        for folder_id in folder_ids:
            cache = self._folders_by_id[project_name][folder_id]
            if cache.is_valid:
                output[folder_id] = cache.get_data()
            elif folder_id:
                folder_ids_to_query.add(folder_id)
            else:
                output[folder_id] = None

        self._query_folder_entities(project_name, folder_ids_to_query)
        for folder_id in folder_ids_to_query:
            cache = self._folders_by_id[project_name][folder_id]
            output[folder_id] = cache.get_data()
        return output

    def get_folder_entity(
        self, project_name: str, folder_id: str
    ) -> dict[str, Any] | None:
        output = self.get_folder_entities(project_name, {folder_id})
        return output[folder_id]

    def get_task_entities(
        self, project_name: str | None, task_ids: set[str] | list[str]
    ) -> dict[str, dict[str, Any]]:
        output = {}
        if not isinstance(task_ids, set):
            task_ids = set(task_ids)

        if not project_name or not task_ids:
            return output

        task_ids_to_query = set()
        for task_id in task_ids:
            cache = self._tasks_by_id[project_name][task_id]
            if cache.is_valid:
                output[task_id] = cache.get_data()
            elif task_id:
                task_ids_to_query.add(task_id)
            else:
                output[task_id] = None
        self._query_task_entities(project_name, task_ids_to_query)
        for task_id in task_ids_to_query:
            cache = self._tasks_by_id[project_name][task_id]
            output[task_id] = cache.get_data()
        return output

    def get_task_entity(
        self, project_name: str, task_id: str
    ) -> dict[str, Any] | None:
        output = self.get_task_entities(project_name, {task_id})
        return output[task_id]

    def get_entity_ids_for_assignees(
        self, project_name: str, assignees: set[str] | list[str]
    ) -> dict[str, set[str]]:
        folder_ids = set()
        task_ids = set()
        output = {
            "folder_ids": folder_ids,
            "task_ids": task_ids,
        }
        assignees = set(assignees)
        for assignee in tuple(assignees):
            cache = self._entity_ids_by_assignee[project_name][assignee]
            if cache.is_valid:
                assignees.discard(assignee)
                assignee_data = cache.get_data()
                folder_ids.update(assignee_data["folder_ids"])
                task_ids.update(assignee_data["task_ids"])

        if not assignees:
            return output

        tasks = ayon_api.get_tasks(
            project_name,
            assignees_all=assignees,
            fields={"id", "folderId", "assignees"},
        )
        tasks_assignee = {}
        for task in tasks:
            folder_ids.add(task["folderId"])
            task_ids.add(task["id"])
            for assignee in task["assignees"]:
                tasks_assignee.setdefault(assignee, []).append(task)

        for assignee, tasks in tasks_assignee.items():
            cache = self._entity_ids_by_assignee[project_name][assignee]
            assignee_folder_ids = set()
            assignee_task_ids = set()
            assignee_data = {
                "folder_ids": assignee_folder_ids,
                "task_ids": assignee_task_ids,
            }
            for task in tasks:
                assignee_folder_ids.add(task["folderId"])
                assignee_task_ids.add(task["id"])
            cache.update_data(assignee_data)

        return output

    def get_available_tags_by_entity_type(
        self, project_name: str
    ) -> dict[str, list[str]]:
        """Get available tags for all entity types in a project."""
        cache = self._tags_by_entity_type.get(project_name)
        if not cache.is_valid:
            tags = None
            if project_name:
                response = ayon_api.get(f"projects/{project_name}/tags")
                if response.status_code == 200:
                    tags = response.data

            # Fake empty tags
            if tags is None:
                tags = {
                    "folders": [],
                    "tasks": [],
                    "products": [],
                    "versions": [],
                    "representations": [],
                    "workfiles": []
                }
            cache.update_data(tags)
        return cache.get_data()

    @contextlib.contextmanager
    def _folder_refresh_event_manager(
        self, project_name: str, sender: str | None
    ) -> Generator[None, None, None]:
        self._folders_refreshing.add(project_name)
        self._controller.emit_event(
            "folders.refresh.started",
            {"project_name": project_name, "sender": sender},
            HIERARCHY_MODEL_SENDER
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                "folders.refresh.finished",
                {"project_name": project_name, "sender": sender},
                HIERARCHY_MODEL_SENDER
            )
            self._folders_refreshing.remove(project_name)

    @contextlib.contextmanager
    def _task_refresh_event_manager(
        self, project_name: str, folder_id: str, sender: str | None
    ) -> Generator[None, None, None]:
        self._tasks_refreshing.add(folder_id)
        self._controller.emit_event(
            "tasks.refresh.started",
            {
                "project_name": project_name,
                "folder_id": folder_id,
                "sender": sender,
            },
            HIERARCHY_MODEL_SENDER
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                "tasks.refresh.finished",
                {
                    "project_name": project_name,
                    "folder_id": folder_id,
                    "sender": sender,
                },
                HIERARCHY_MODEL_SENDER
            )
            self._tasks_refreshing.discard(folder_id)

    def _refresh_folders_cache(
        self, project_name: str, sender: str | None = None
    ) -> None:
        if project_name in self._folders_refreshing:
            return

        with self._folder_refresh_event_manager(project_name, sender):
            folder_items = self._query_folders(project_name)
            self._folders_items[project_name].update_data(folder_items)

    def _query_folders(self, project_name: str) -> dict[str, FolderItem]:
        hierarchy = ayon_api.get_folders_hierarchy(project_name)

        folder_items = {}
        hierachy_queue = collections.deque(hierarchy["hierarchy"])
        while hierachy_queue:
            item = hierachy_queue.popleft()
            folder_item = FolderItem.from_hierarchy_item(item)
            folder_items[folder_item.entity_id] = folder_item
            hierachy_queue.extend(item["children"] or [])
        return folder_items

    def _query_folder_entities(
        self, project_name: str, folder_ids: set[str]
    ) -> None:
        if not folder_ids:
            return
        project_cache = self._folders_by_id[project_name]
        folders = ayon_api.get_folders(project_name, folder_ids=folder_ids)
        for folder in folders:
            folder_id = folder["id"]
            project_cache[folder_id].update_data(folder)

    def _query_task_entities(
        self, project_name: str, task_ids: set[str]
    ) -> None:
        if not task_ids:
            return

        project_cache = self._tasks_by_id[project_name]
        tasks = ayon_api.get_tasks(project_name, task_ids=task_ids)
        for task in tasks:
            task_id = task["id"]
            project_cache[task_id].update_data(task)

    def _refresh_tasks_cache(
        self, project_name: str, folder_id: str, sender: str | None = None
    ) -> None:
        if folder_id in self._tasks_refreshing:
            while folder_id in self._tasks_refreshing:
                time.sleep(0.01)
            return

        cache = self._task_items[project_name][folder_id]
        with self._task_refresh_event_manager(
            project_name, folder_id, sender
        ):
            cache.update_data(self._query_tasks(project_name, folder_id))

    def _query_tasks(
        self, project_name: str, folder_id: str
    ) -> list[TaskItem]:
        tasks = list(ayon_api.get_tasks(
            project_name,
            folder_ids=[folder_id],
            fields={"id", "name", "label", "folderId", "type", "tags"}
        ))
        task_type_items: list[TaskTypeItem] = (
            self._controller.get_task_type_items(project_name)
        )

        order_by_task_type = {
            task_type.name: index
            for index, task_type in enumerate(task_type_items)
        }
        return [
            TaskItem.from_entity(task, order_by_task_type[task["type"]])
            for task in tasks
        ]
