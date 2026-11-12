from __future__ import annotations

from abc import ABC, abstractmethod
import collections
import contextlib
from dataclasses import dataclass
import threading
import time
from typing import Any, Generator

import ayon_api

from ayon_core.lib import NestedCacheItem

from .projects import TaskTypeItem
from .websocket import Event, EventCallback, get_existing_event_hub

HIERARCHY_MODEL_SENDER = "hierarchy.model"
FOLDER_FIELDS = {
    "id",
    "name",
    "label",
    "parentId",
    "path",
    "folderType",
    "status",
}


# Server events that change folder items or the folders hierarchy. Other
#   folder events (attributes, data, tags, thumbnail) don't affect them.
_FOLDER_ITEMS_TOPICS = (
    "entity.folder.created",
    "entity.folder.deleted",
    "entity.folder.renamed",
    "entity.folder.parent_changed",
    "entity.folder.active_changed",
    "entity.folder.label_changed",
    "entity.folder.status_changed",
    "entity.folder.type_changed",
)
# Project events that can change folder items without any folder event,
#   e.g. renaming a folder type or a status in project anatomy renames it
#   on all folders.
_PROJECT_TOPICS = (
    "entity.project.changed",
    "entity.project.deleted",
    "entity.project.renamed",
)


@dataclass
class _FoldersCacheEntry:
    """Cached folder items of one project.

    Attributes:
        items (dict[str, FolderItem]): Folder items by id.
        queried_at (float): When the query started ('time.monotonic').
        listening (bool): Server events about folders were received
            for the whole time since the query started.
        changed (bool): A server event changed folders of the project
            since the query started.
        listening_lost_at (float | None): When websocket connection was
            lost while the entry was listening ('time.monotonic').

    """
    items: dict[str, FolderItem]
    queried_at: float
    listening: bool
    changed: bool = False
    listening_lost_at: float | None = None


@dataclass
class _FoldersQueryToken:
    """State of the cache when a query of folders started."""
    queried_at: float
    reset_counter: int
    project_reset_counter: int
    change_counter: int
    connection_counter: int
    listening: bool


class _SharedFoldersCache:
    """Folder items cache shared by all 'HierarchyModel' instances.

    Each tool (loader, publisher, workfiles, ...) has its own controller
    with its own 'HierarchyModel', but the folder hierarchy of a project is
    the same for all of them. Sharing the cache means the full folder list
    of a project is queried once per process instead of once per tool.

    Cached folders are valid for 'min_lifetime' seconds. When the
    websocket of the process is connected, the cache listens to server
    events about folders, and folders are kept until an event changes
    them, or until the user explicitly asks for a refresh (forced reset).
    A change does not trigger a new query, folders are queried again when
    a tool asks for them, but not more often than once per
    'min_lifetime', even if folders change all the time.

    When websocket connection is lost, cached folders are not cleared.
    Events might be missed while disconnected and server does not allow
    regular users to query events of other users, so folders that were
    kept by events are valid for 'min_lifetime' since the connection was
    lost, then they are queried once again.

    The websocket connection is not created by the cache. It is created
    by tools that process server events (see 'WSEventsModel'), so headless
    usage stays without websocket and uses only 'min_lifetime'.

    """
    min_lifetime = 5 * 60  # 5 minutes
    # Seconds until new topics subscription is sent to server when
    #   websocket is already connected. Server sends heartbeat every
    #   5 seconds, the subscription is sent after a message is received.
    subscribe_delay = 10

    def __init__(self) -> None:
        # Used as lock for all attributes below
        self.cond = threading.Condition()
        # Project name -> ident of thread refreshing its folders
        self.refreshing: dict[str, int] = {}

        self._entries: dict[str, _FoldersCacheEntry] = {}
        self._reset_counter = 0
        self._project_reset_counters: dict[str, int] = (
            collections.defaultdict(int)
        )
        self._change_counters: dict[str, int] = collections.defaultdict(int)
        self._connection_counter = 0
        # Since when are folder events received ('time.monotonic')
        self._listening_since: float | None = None

        self._register_lock = threading.Lock()
        self._subscribed_at: float | None = None
        self._hub_callbacks: list[EventCallback] = []

    def reset(self, project_name: str | None = None) -> None:
        """Clear cached folders.

        Results of queries running at the moment are discarded.

        Args:
            project_name (str | None): Clear only folders of the project.

        """
        with self.cond:
            if project_name is None:
                self._entries.clear()
                self._reset_counter += 1
            else:
                self._entries.pop(project_name, None)
                self._project_reset_counters[project_name] += 1

    def get_valid_items(
        self, project_name: str
    ) -> dict[str, FolderItem] | None:
        """Folder items of a project if cache is valid.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, FolderItem] | None: Folder items by id, 'None' if
                folders have to be queried.

        """
        self._listen_to_events()
        with self.cond:
            return self.get_valid_items_locked(project_name)

    def get_valid_items_locked(
        self, project_name: str
    ) -> dict[str, FolderItem] | None:
        """Same as 'get_valid_items', but caller holds 'cond'."""
        entry = self._entries.get(project_name)
        if entry is None or not self._is_entry_valid(entry):
            return None
        return entry.items

    def get_items(self, project_name: str) -> dict[str, FolderItem]:
        """Last queried folder items of a project, even if not valid.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, FolderItem]: Folder items by id.

        """
        with self.cond:
            entry = self._entries.get(project_name)
            if entry is None:
                return {}
            return entry.items

    def start_query_locked(self, project_name: str) -> _FoldersQueryToken:
        """Remember cache state before folders are queried.

        Caller holds 'cond'.

        Args:
            project_name (str): Project name.

        Returns:
            _FoldersQueryToken: Token to pass to 'store'.

        """
        now = self._now()
        listening_since = self._listening_since
        return _FoldersQueryToken(
            queried_at=now,
            reset_counter=self._reset_counter,
            project_reset_counter=self._project_reset_counters[project_name],
            change_counter=self._change_counters[project_name],
            connection_counter=self._connection_counter,
            listening=(
                listening_since is not None and now >= listening_since
            ),
        )

    def store(
        self,
        project_name: str,
        items: dict[str, FolderItem],
        token: _FoldersQueryToken,
    ) -> bool:
        """Store queried folder items.

        Args:
            project_name (str): Project name.
            items (dict[str, FolderItem]): Folder items by id.
            token (_FoldersQueryToken): Token from 'start_query_locked'.

        Returns:
            bool: Items were stored. 'False' if cache was reset while
                the query was running and folders have to be queried
                again.

        """
        with self.cond:
            if (
                token.reset_counter != self._reset_counter
                or token.project_reset_counter
                != self._project_reset_counters[project_name]
            ):
                return False

            self._entries[project_name] = _FoldersCacheEntry(
                items=items,
                queried_at=token.queried_at,
                listening=(
                    token.listening
                    and token.connection_counter == self._connection_counter
                ),
                # Change during the query might not be in the result
                changed=(
                    token.change_counter
                    != self._change_counters[project_name]
                ),
            )
            return True

    def _now(self) -> float:
        return time.monotonic()

    def _is_entry_valid(self, entry: _FoldersCacheEntry) -> bool:
        if entry.listening and not entry.changed:
            return True
        valid_from = entry.queried_at
        if entry.listening_lost_at is not None:
            valid_from = max(valid_from, entry.listening_lost_at)
        return self._now() - valid_from < self.min_lifetime

    def _listen_to_events(self) -> None:
        """Register callbacks to server events once websocket exists."""
        if self._hub_callbacks:
            return

        event_hub = get_existing_event_hub()
        if event_hub is None:
            return

        with self._register_lock:
            if self._hub_callbacks:
                return
            subscribed_at = self._now()
            with self.cond:
                self._subscribed_at = subscribed_at
                if event_hub.is_connected():
                    # Subscription is sent with next message
                    self._listening_since = (
                        subscribed_at + self.subscribe_delay
                    )

            callbacks = [
                EventCallback(
                    "connection.opened", self._on_connection_opened
                ),
                EventCallback(
                    "connection.closed", self._on_connection_closed
                ),
            ]
            for topic in _FOLDER_ITEMS_TOPICS + _PROJECT_TOPICS:
                callbacks.append(
                    EventCallback(topic, self._on_folders_changed)
                )
            event_hub.add_callbacks(callbacks, connect=False)
            self._hub_callbacks = callbacks

    def _on_connection_opened(self) -> None:
        with self.cond:
            # Subscription might have been sent with the previous message
            #   if callbacks were registered during connection.
            self._listening_since = max(
                self._now(),
                self._subscribed_at + self.subscribe_delay,
            )

    def _on_connection_closed(self) -> None:
        # Events might be missed until connection is opened again. Keep
        #   folders that were up to date for 'min_lifetime', so a brief
        #   interruption does not cause queries.
        now = self._now()
        with self.cond:
            self._listening_since = None
            self._connection_counter += 1
            for entry in self._entries.values():
                if entry.listening and not entry.changed:
                    entry.listening_lost_at = now
                entry.listening = False

    def _on_folders_changed(self, event: Event) -> None:
        project_names = {event.project_name}
        # Project rename event does not have project name filled
        if isinstance(event.summary, dict):
            project_names.add(event.summary.get("entityName"))
        project_names.discard(None)
        if not project_names:
            return

        with self.cond:
            for project_name in project_names:
                self._change_counters[project_name] += 1
                entry = self._entries.get(project_name)
                if entry is not None:
                    entry.changed = True


_SHARED_FOLDERS_CACHE = _SharedFoldersCache()


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
        entity_id (str): Folder id.
        parent_id (str | None): Parent folder id. If 'None' then project
            is parent.
        name (str): Name of folder.
        path (str): Folder path.
        folder_type (str): Type of folder.
        label (str): Folder label.
        status (str): Folder status name.
    """
    # TODO: Use `@dataclass(slots=True)` when we drop Python 3.9 support.
    __slots__ = (
        "entity_id",
        "parent_id",
        "name",
        "path",
        "folder_type",
        "label",
        "status",
    )
    entity_id: str
    parent_id: str | None
    name: str
    path: str
    folder_type: str
    label: str
    status: str

    def to_data(self) -> dict[str, str | None]:
        """Converts folder item to data.

        Returns:
            dict[str, str | None]: Folder item data.

        """
        return dict(
            entity_id=self.entity_id,
            parent_id=self.parent_id,
            name=self.name,
            path=self.path,
            folder_type=self.folder_type,
            label=self.label,
            status=self.status,
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

    @classmethod
    def from_rest_data(cls, data: dict[str, Any]) -> FolderItem:
        """Creates folder item from 'get_rest_folders' flat item.

        Args:
            data (dict[str, Any]): Flat folder item from REST endpoint.

        """
        name = data["name"]
        return cls(
            entity_id=data["id"],
            parent_id=data["parentId"],
            name=name,
            path=f"/{data['path']}",
            folder_type=data["folderType"],
            label=data["label"] or name,
            status=data["status"],
        )

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> FolderItem:
        name = entity["name"]
        return FolderItem(
            entity_id=entity["id"],
            parent_id=entity["parentId"],
            name=name,
            path=entity["path"],
            folder_type=entity["folderType"],
            label=entity["label"] or name,
            status=entity["status"]
        )


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
        parent_id (str): Parent folder id.
        tags (list[str]): List of tags assigned to task.
        full_label (str): Full label of task. Is filled automatically.
        status (str): Task status name.
    """
    task_id: str
    name: str
    label: str
    task_type: str
    task_type_order: int
    parent_id: str
    tags: list[str]
    status: str
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

    def to_data(self) -> dict[str, Any]:
        """Converts task item to data.

        Returns:
            dict[str, Any]: Task item data.

        """
        return dict(
            task_id=self.task_id,
            name=self.name,
            label=self.label,
            parent_id=self.parent_id,
            task_type=self.task_type,
            task_type_order=self.task_type_order,
            tags=self.tags.copy(),
            full_label=self.full_label,
            status=self.status,
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
            label=entity["label"] or entity["name"],
            task_type=entity["type"],
            task_type_order=task_type_order,
            parent_id=entity["folderId"],
            tags=entity["tags"],
            status=entity["status"]
        )


class HierarchyModel:
    """Model for project hierarchy items.

    Hierarchy items are folders and tasks. Folders can have as parent another
    folder or project. Tasks can have as parent only folder.

    Folder items are stored in a cache shared by all instances of the model
    (see '_SharedFoldersCache'), other caches are per instance.
    """
    lifetime = 60  # A minute

    def __init__(self, controller):
        self._tags_by_entity_type = NestedCacheItem(
            levels=1, default_factory=dict, lifetime=self.lifetime)
        self._folders_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._task_items = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)
        self._tasks_by_id = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._entity_ids_by_assignee = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime)

        self._tasks_refreshing = set()
        self._controller = controller

    def reset(self, force: bool = False) -> None:
        """Reset cached data.

        Folder items are shared with other tools and are not reset by
        default. They are queried again once they change on server or
        their cache lifetime expires (see '_SharedFoldersCache').

        Args:
            force (bool): Reset also folder items shared with other tools.
                Should be used when user explicitly asks for a refresh.

        """
        if force:
            _SHARED_FOLDERS_CACHE.reset()
        self._tags_by_entity_type.reset()
        self._folders_by_id.reset()

        self._task_items.reset()
        self._tasks_by_id.reset()

        self._entity_ids_by_assignee.reset()

    def refresh_project(self, project_name: str) -> None:
        """Force to refresh folder items for a project.

        Args:
            project_name (str): Name of project to refresh.

        """
        _SHARED_FOLDERS_CACHE.reset(project_name)
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
        items = _SHARED_FOLDERS_CACHE.get_valid_items(project_name)
        if items is None:
            self._refresh_folders_cache(project_name, sender)
            items = _SHARED_FOLDERS_CACHE.get_items(project_name)
        return items

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

        cache_data = _SHARED_FOLDERS_CACHE.get_valid_items(project_name)
        if cache_data is not None:
            return {
                folder_id: cache_data.get(folder_id)
                for folder_id in folder_ids
            }

        folders = ayon_api.get_folders(
            project_name,
            folder_ids=folder_ids,
            fields=FOLDER_FIELDS,
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

        cache_data = _SHARED_FOLDERS_CACHE.get_valid_items(project_name)
        if cache_data is not None:
            for folder_item in cache_data.values():
                if folder_item.path in folder_paths:
                    output[folder_item.path] = folder_item
            return output
        folders = ayon_api.get_folders(
            project_name,
            folder_paths=folder_paths,
            fields=FOLDER_FIELDS,
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
        cache = _SHARED_FOLDERS_CACHE
        thread_id = threading.get_ident()
        cond = cache.cond
        while True:
            with cond:
                refreshing_thread = cache.refreshing.get(project_name)
                # Re-entered from a refresh event callback in the same thread
                if refreshing_thread == thread_id:
                    return
                # Other thread is already querying, wait for its result
                #   instead of returning not yet filled cache.
                if refreshing_thread is not None:
                    cond.wait_for(
                        lambda: project_name not in cache.refreshing
                    )
                    # Query again if the result was discarded or failed
                    if cache.get_valid_items_locked(project_name) is None:
                        continue
                    return

                cache.refreshing[project_name] = thread_id
                token = cache.start_query_locked(project_name)

            stored = False
            try:
                with self._folder_refresh_event_manager(project_name, sender):
                    folder_items = self._query_folders(project_name)
                    stored = cache.store(project_name, folder_items, token)
            finally:
                with cond:
                    cache.refreshing.pop(project_name, None)
                    cond.notify_all()

            if stored:
                return
            # Cache was reset during the query, the result might be
            #   outdated so query again

    def _query_folders(self, project_name: str) -> dict[str, FolderItem]:
        folders = ayon_api.get_rest_folders(project_name, include_attrib=False)
        folders_by_parent_id = collections.defaultdict(list)
        for folder in folders:
            folders_by_parent_id[folder["parentId"]].append(folder)

        # REST endpoint does not filter inactive folders, skip them
        #   and their descendants
        output = {}
        hierarchy_queue = collections.deque()
        hierarchy_queue.append(None)
        while hierarchy_queue:
            parent_id = hierarchy_queue.popleft()
            for folder in folders_by_parent_id[parent_id]:
                if not folder.get("active", True):
                    continue
                folder_id = folder["id"]
                output[folder_id] = FolderItem.from_rest_data(folder)
                hierarchy_queue.append(folder_id)
        return output

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
            fields={
                "id",
                "name",
                "label",
                "folderId",
                "type",
                "tags",
                "status",
            }
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
