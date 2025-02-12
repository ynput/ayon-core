from __future__ import annotations

import time
import collections
import contextlib
import typing
from abc import ABC, abstractmethod

import ayon_api

from ayon_core.lib import NestedCacheItem

if typing.TYPE_CHECKING:
    from typing import Union

HIERARCHY_MODEL_SENDER = "hierarchy.model"


class AbstractHierarchyController(ABC):
    @abstractmethod
    def emit_event(self, topic, data, source):
        pass


class FolderItem:
    """Item representing folder entity on a server.

    Folder can be a child of another folder or a project.

    Args:
        entity_id (str): Folder id.
        parent_id (Union[str, None]): Parent folder id. If 'None' then project
            is parent.
        name (str): Name of folder.
        path (str): Folder path.
        folder_type (str): Type of folder.
        label (Union[str, None]): Folder label.
    """

    def __init__(
        self, entity_id, parent_id, name, path, folder_type, label
    ):
        self.entity_id = entity_id
        self.parent_id = parent_id
        self.name = name
        self.path = path
        self.folder_type = folder_type
        self.label = label or name

    def to_data(self):
        """Converts folder item to data.

        Returns:
            dict[str, Any]: Folder item data.
        """

        return {
            "entity_id": self.entity_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "path": self.path,
            "folder_type": self.folder_type,
            "label": self.label,
        }

    @classmethod
    def from_data(cls, data):
        """Re-creates folder item from data.

        Args:
            data (dict[str, Any]): Folder item data.

        Returns:
            FolderItem: Folder item.
        """

        return cls(**data)


class TaskItem:
    """Task item representing task entity on a server.

    Task is child of a folder.

    Task item has label that is used for display in UI. The label is by
        default using task name and type.

    Args:
        task_id (str): Task id.
        name (str): Name of task.
        name (Union[str, None]): Task label.
        task_type (str): Type of task.
        parent_id (str): Parent folder id.
    """

    def __init__(
        self,
        task_id: str,
        name: str,
        label: Union[str, None],
        task_type: str,
        parent_id: str,
    ):
        self.task_id = task_id
        self.name = name
        self.label = label
        self.task_type = task_type
        self.parent_id = parent_id

        self._full_label = None

    @property
    def id(self):
        """Alias for task_id.

        Returns:
            str: Task id.
        """

        return self.task_id

    @property
    def full_label(self):
        """Label of task item for UI.

        Returns:
            str: Label of task item.
        """

        if self._full_label is None:
            label = self.label or self.name
            self._full_label = f"{label} ({self.task_type})"
        return self._label

    def to_data(self):
        """Converts task item to data.

        Returns:
            dict[str, Any]: Task item data.
        """

        return {
            "task_id": self.task_id,
            "name": self.name,
            "label": self.label,
            "parent_id": self.parent_id,
            "task_type": self.task_type,
        }

    @classmethod
    def from_data(cls, data):
        """Re-create task item from data.

        Args:
            data (dict[str, Any]): Task item data.

        Returns:
            TaskItem: Task item.
        """

        return cls(**data)


def _get_task_items_from_tasks(tasks):
    """

    Returns:
        TaskItem: Task item.
    """

    output = []
    for task in tasks:
        folder_id = task["folderId"]
        output.append(TaskItem(
            task["id"],
            task["name"],
            task["label"],
            task["type"],
            folder_id
        ))
    return output


def _get_folder_item_from_hierarchy_item(item):
    name = item["name"]
    path_parts = list(item["parents"])
    path_parts.append(name)
    path = "/" + "/".join(path_parts)
    return FolderItem(
        item["id"],
        item["parentId"],
        name,
        path,
        item["folderType"],
        item["label"]
    )


def _get_folder_item_from_entity(entity):
    name = entity["name"]
    return FolderItem(
        entity["id"],
        entity["parentId"],
        name,
        entity["path"],
        entity["folderType"],
        entity["label"] or name
    )


class HierarchyModel(object):
    """Model for project hierarchy items.

    Hierarchy items are folders and tasks. Folders can have as parent another
    folder or project. Tasks can have as parent only folder.
    """
    lifetime = 60  # A minute

    def __init__(self, controller):
        self._folders_items = NestedCacheItem(
            levels=1, default_factory=dict, lifetime=self.lifetime)
        self._folders_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._task_items = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)
        self._tasks_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._folders_refreshing = set()
        self._tasks_refreshing = set()
        self._controller = controller

    def reset(self):
        self._folders_items.reset()
        self._folders_by_id.reset()

        self._task_items.reset()
        self._tasks_by_id.reset()

    def refresh_project(self, project_name):
        """Force to refresh folder items for a project.

        Args:
            project_name (str): Name of project to refresh.
        """

        self._refresh_folders_cache(project_name)

    def get_folder_items(self, project_name, sender):
        """Get folder items by project name.

        The folders are cached per project name. If the cache is not valid
        then the folders are queried from server.

        Args:
            project_name (str): Name of project where to look for folders.
            sender (Union[str, None]): Who requested the folder ids.

        Returns:
            dict[str, FolderItem]: Folder items by id.
        """

        if not self._folders_items[project_name].is_valid:
            self._refresh_folders_cache(project_name, sender)
        return self._folders_items[project_name].get_data()

    def get_folder_items_by_id(self, project_name, folder_ids):
        """Get folder items by ids.

        This function will query folders if they are not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_ids (Iterable[str]): Folder ids.

        Returns:
            dict[str, Union[FolderItem, None]]: Folder items by id.
        """

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
            folder["id"]: _get_folder_item_from_entity(folder)
            for folder in folders
        })
        return output

    def get_folder_items_by_paths(self, project_name, folder_paths):
        """Get folder items by ids.

        This function will query folders if they are not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_paths (Iterable[str]): Folder paths.

        Returns:
            dict[str, Union[FolderItem, None]]: Folder items by id.
        """

        folder_paths = set(folder_paths)
        output = {folder_path: None for folder_path in folder_paths}
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
            item = _get_folder_item_from_entity(folder)
            output[item.path] = item
        return output

    def get_folder_item(self, project_name, folder_id):
        """Get folder item by id.

        This function will query folder if they is not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_id (str): Folder id.

        Returns:
            Union[FolderItem, None]: Folder item.
        """
        items = self.get_folder_items_by_id(
            project_name, [folder_id]
        )
        return items.get(folder_id)

    def get_folder_item_by_path(self, project_name, folder_path):
        """Get folder item by path.

        This function will query folder if they is not in cache. But the
        queried items are not added to cache back.

        Args:
            project_name (str): Name of project where to look for folders.
            folder_path (str): Folder path.

        Returns:
            Union[FolderItem, None]: Folder item.

        """
        items = self.get_folder_items_by_paths(
            project_name, [folder_path]
        )
        return items.get(folder_path)

    def get_task_item_by_name(
        self, project_name, folder_id, task_name, sender
    ):
        """Get task item by name and folder id.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.
            task_name (str): Task name.
            sender (Union[str, None]): Who requested the task item.

        Returns:
            Optional[TaskItem]: Task item found by name and folder id.

        """
        for task_item in self.get_task_items(project_name, folder_id, sender):
            if task_item.name == task_name:
                return task_item
        return None

    def get_task_items(self, project_name, folder_id, sender):
        if not project_name or not folder_id:
            return []

        task_cache = self._task_items[project_name][folder_id]
        if not task_cache.is_valid:
            self._refresh_tasks_cache(project_name, folder_id, sender)
        return task_cache.get_data()

    def get_folder_entities(self, project_name, folder_ids):
        """Get folder entities by ids.

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.

        Returns:
            dict[str, Any]: Folder entities by id.
        """

        output = {}
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

    def get_folder_entity(self, project_name, folder_id):
        output = self.get_folder_entities(project_name, {folder_id})
        return output[folder_id]

    def get_task_entities(self, project_name, task_ids):
        output = {}
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

    def get_task_entity(self, project_name, task_id):
        output = self.get_task_entities(project_name, {task_id})
        return output[task_id]

    @contextlib.contextmanager
    def _folder_refresh_event_manager(self, project_name, sender):
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
        self, project_name, folder_id, sender
    ):
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

    def _refresh_folders_cache(self, project_name, sender=None):
        if project_name in self._folders_refreshing:
            return

        with self._folder_refresh_event_manager(project_name, sender):
            folder_items = self._query_folders(project_name)
            self._folders_items[project_name].update_data(folder_items)

    def _query_folders(self, project_name):
        hierarchy = ayon_api.get_folders_hierarchy(project_name)

        folder_items = {}
        hierachy_queue = collections.deque(hierarchy["hierarchy"])
        while hierachy_queue:
            item = hierachy_queue.popleft()
            folder_item = _get_folder_item_from_hierarchy_item(item)
            folder_items[folder_item.entity_id] = folder_item
            hierachy_queue.extend(item["children"] or [])
        return folder_items

    def _query_folder_entities(self, project_name, folder_ids):
        if not project_name or not folder_ids:
            return
        project_cache = self._folders_by_id[project_name]
        folders = ayon_api.get_folders(project_name, folder_ids=folder_ids)
        for folder in folders:
            folder_id = folder["id"]
            project_cache[folder_id].update_data(folder)

    def _query_task_entities(self, project_name, task_ids):
        if not project_name or not task_ids:
            return

        project_cache = self._tasks_by_id[project_name]
        tasks = ayon_api.get_tasks(project_name, task_ids=task_ids)
        for task in tasks:
            task_id = task["id"]
            project_cache[task_id].update_data(task)

    def _refresh_tasks_cache(self, project_name, folder_id, sender=None):
        if folder_id in self._tasks_refreshing:
            while folder_id in self._tasks_refreshing:
                time.sleep(0.01)
            return

        cache = self._task_items[project_name][folder_id]
        with self._task_refresh_event_manager(
            project_name, folder_id, sender
        ):
            cache.update_data(self._query_tasks(project_name, folder_id))

    def _query_tasks(self, project_name, folder_id):
        tasks = list(ayon_api.get_tasks(
            project_name,
            folder_ids=[folder_id],
            fields={"id", "name", "label", "folderId", "type"}
        ))
        return _get_task_items_from_tasks(tasks)
