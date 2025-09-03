from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass

import ayon_api

from ayon_core.style import get_default_entity_icon_color
from ayon_core.lib import CacheItem, NestedCacheItem

PROJECTS_MODEL_SENDER = "projects.model"


class StatusStates:
    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"


class AbstractHierarchyController(ABC):
    @abstractmethod
    def emit_event(self, topic, data, source):
        pass


class StatusItem:
    """Item representing status of project.

    Args:
        name (str): Status name ("Not ready").
        color (str): Status color in hex ("#434a56").
        short (str): Short status name ("NRD").
        icon (str): Icon name in MaterialIcons ("fiber_new").
        state (str): Status state.

    """
    def __init__(
        self,
        name: str,
        color: str,
        short: str,
        icon: str,
        state: str
    ):
        self.name: str = name
        self.color: str = color
        self.short: str = short
        self.icon: str = icon
        self.state: str = state

    def to_data(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "color": self.color,
            "short": self.short,
            "icon": self.icon,
            "state": self.state,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)

    @classmethod
    def from_project_item(cls, status_data):
        return cls(
            name=status_data["name"],
            color=status_data["color"],
            short=status_data["shortName"],
            icon=status_data["icon"],
            state=status_data["state"],
        )


@dataclass
class TagItem:
    """Tag definition set on project anatomy."""
    name: str
    color: str


class FolderTypeItem:
    """Item representing folder type of project.

    Args:
        name (str): Folder type name ("Shot").
        short (str): Short folder type name ("sh").
        icon (str): Icon name in MaterialIcons ("fiber_new").

    """
    def __init__(self, name, short, icon):
        self.name = name
        self.short = short
        self.icon = icon

    def to_data(self):
        return {
            "name": self.name,
            "short": self.short,
            "icon": self.icon,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)

    @classmethod
    def from_project_item(cls, folder_type_data):
        return cls(
            name=folder_type_data["name"],
            short=folder_type_data.get("shortName", ""),
            icon=folder_type_data["icon"],
        )


class TaskTypeItem:
    """Item representing task type of project.

    Args:
        name (str): Task type name ("Shot").
        short (str): Short task type name ("sh").
        icon (str): Icon name in MaterialIcons ("fiber_new").

    """
    def __init__(self, name, short, icon):
        self.name = name
        self.short = short
        self.icon = icon

    def to_data(self):
        return {
            "name": self.name,
            "short": self.short,
            "icon": self.icon,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)

    @classmethod
    def from_project_item(cls, task_type_data):
        return cls(
            name=task_type_data["name"],
            short=task_type_data["shortName"],
            icon=task_type_data["icon"],
        )


@dataclass
class ProjectItem:
    """Item representing folder entity on a server.

    Folder can be a child of another folder or a project.

    Args:
        name (str): Project name.
        active (Union[str, None]): Parent folder id. If 'None' then project
            is parent.
    """
    name: str
    active: bool
    is_library: bool
    icon: dict[str, Any]
    is_pinned: bool = False

    @classmethod
    def from_entity(cls, project_entity: dict[str, Any]) -> "ProjectItem":
        """Creates folder item from entity.

        Args:
            project_entity (dict[str, Any]): Project entity.

        Returns:
            ProjectItem: Project item.

        """
        icon = {
            "type": "awesome-font",
            "name": "fa.book" if project_entity["library"] else "fa.map",
            "color": get_default_entity_icon_color(),
        }
        return cls(
            project_entity["name"],
            project_entity["active"],
            project_entity["library"],
            icon
        )

    def to_data(self):
        """Converts folder item to data.

        Returns:
            dict[str, Any]: Folder item data.
        """

        return {
            "name": self.name,
            "active": self.active,
            "is_library": self.is_library,
            "icon": self.icon,
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


def _get_project_items_from_entitiy(
    projects: list[dict[str, Any]]
) -> list[ProjectItem]:
    """

    Args:
        projects (list[dict[str, Any]]): List of projects.

    Returns:
        list[ProjectItem]: Project item.

    """
    return [
        ProjectItem.from_entity(project)
        for project in projects
    ]


class ProjectsModel(object):
    def __init__(self, controller):
        self._projects_cache = CacheItem(default_factory=list)
        self._projects_by_name = NestedCacheItem(
            levels=1, default_factory=list
        )
        self._project_statuses_cache = {}
        self._folder_types_cache = {}
        self._task_types_cache = {}

        self._is_refreshing = False
        self._controller = controller

    def reset(self):
        self._project_statuses_cache = {}
        self._folder_types_cache = {}
        self._task_types_cache = {}
        self._projects_cache.reset()
        self._projects_by_name.reset()

    def refresh(self):
        """Refresh project items.

        This method will requery list of ProjectItem returned by
        'get_project_items'.

        To reset all cached items use 'reset' method.
        """
        self._refresh_projects_cache()

    def get_project_items(self, sender):
        """

        Args:
            sender (str): Name of sender who asked for items.

        Returns:
            Union[list[ProjectItem], None]: List of project items, or None
                if model is refreshing.
        """

        if not self._projects_cache.is_valid:
            return self._refresh_projects_cache(sender)
        return self._projects_cache.get_data()

    def get_project_entity(self, project_name):
        """Get project entity.

        Args:
            project_name (str): Project name.

        Returns:
            Union[dict[str, Any], None]: Project entity or None if project
                was not found by name.

        """
        project_cache = self._projects_by_name[project_name]
        if not project_cache.is_valid:
            entity = None
            if project_name:
                entity = ayon_api.get_project(project_name)
            project_cache.update_data(entity)
        return project_cache.get_data()

    def get_project_anatomy_tags(self, project_name: str) -> list[TagItem]:
        """Get project anatomy tags.

        Args:
            project_name (str): Project name.

        Returns:
            list[TagItem]: Tag definitions.

        """
        project_entity = self.get_project_entity(project_name)
        return [
            TagItem(tag["name"], tag["color"])
            for tag in project_entity["tags"]
        ]

    def get_project_status_items(self, project_name, sender):
        """Get project status items.

        Args:
            project_name (str): Project name.
            sender (Union[str, None]): Name of sender who asked for items.

        Returns:
            list[StatusItem]: Status items for project.

        """
        if project_name is None:
            return []

        statuses_cache = self._project_statuses_cache.get(project_name)
        if (
            statuses_cache is not None
            and not self._projects_cache.is_valid
        ):
            statuses_cache = None

        if statuses_cache is None:
            with self._project_items_refresh_event_manager(
                sender, project_name, "statuses"
            ):
                project_entity = self.get_project_entity(project_name)
                statuses = []
                if project_entity:
                    statuses = [
                        StatusItem.from_project_item(status)
                        for status in project_entity["statuses"]
                    ]
                statuses_cache = statuses
            self._project_statuses_cache[project_name] = statuses_cache
        return list(statuses_cache)

    def get_folder_type_items(self, project_name, sender):
        """Get project status items.

        Args:
            project_name (str): Project name.
            sender (Union[str, None]): Name of sender who asked for items.

        Returns:
            list[FolderType]: Folder type items for project.

        """
        return self._get_project_items(
            project_name,
            sender,
            "folder_types",
            self._folder_types_cache,
            self._folder_type_items_getter,
        )

    def get_task_type_items(self, project_name, sender):
        """Get project task type items.

        Args:
            project_name (str): Project name.
            sender (Union[str, None]): Name of sender who asked for items.

        Returns:
            list[TaskTypeItem]: Task type items for project.

        """
        return self._get_project_items(
            project_name,
            sender,
            "task_types",
            self._task_types_cache,
            self._task_type_items_getter,
        )

    def _get_project_items(
        self, project_name, sender, item_type, cache_obj, getter
    ):
        if (
            project_name in cache_obj
            and (
                project_name is None
                or self._projects_by_name[project_name].is_valid
            )
        ):
            return cache_obj[project_name]

        with self._project_items_refresh_event_manager(
            sender, project_name, item_type
        ):
            cache_value = getter(self.get_project_entity(project_name))
        cache_obj[project_name] = cache_value
        return cache_value

    @contextlib.contextmanager
    def _project_refresh_event_manager(self, sender):
        self._is_refreshing = True
        self._controller.emit_event(
            "projects.refresh.started",
            {"sender": sender},
            PROJECTS_MODEL_SENDER
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                "projects.refresh.finished",
                {"sender": sender},
                PROJECTS_MODEL_SENDER
            )
            self._is_refreshing = False

    @contextlib.contextmanager
    def _project_items_refresh_event_manager(
        self, sender, project_name, item_type
    ):
        self._controller.emit_event(
            f"projects.{item_type}.refresh.started",
            {"sender": sender, "project_name": project_name},
            PROJECTS_MODEL_SENDER
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                f"projects.{item_type}.refresh.finished",
                {"sender": sender, "project_name": project_name},
                PROJECTS_MODEL_SENDER
            )

    def _refresh_projects_cache(self, sender=None):
        if self._is_refreshing:
            return None

        with self._project_refresh_event_manager(sender):
            project_items = self._query_projects()
            self._projects_cache.update_data(project_items)
        return self._projects_cache.get_data()

    def _query_projects(self) -> list[ProjectItem]:
        projects = ayon_api.get_projects(fields=["name", "active", "library"])
        user = ayon_api.get_user()
        pinned_projects = (
            user
            .get("data", {})
            .get("frontendPreferences", {})
            .get("pinnedProjects")
        ) or []
        pinned_projects = set(pinned_projects)
        project_items = _get_project_items_from_entitiy(list(projects))
        for project in project_items:
            project.is_pinned = project.name in pinned_projects
        return project_items

    def _status_items_getter(self, project_entity):
        if not project_entity:
            return []
        return [
            StatusItem.from_project_item(status)
            for status in project_entity["statuses"]
        ]

    def _folder_type_items_getter(self, project_entity):
        if not project_entity:
            return []
        return [
            FolderTypeItem.from_project_item(folder_type)
            for folder_type in project_entity["folderTypes"]
        ]

    def _task_type_items_getter(self, project_entity):
        if not project_entity:
            return []
        return [
            TaskTypeItem.from_project_item(task_type)
            for task_type in project_entity["taskTypes"]
        ]
