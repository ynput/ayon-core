import contextlib
from abc import ABCMeta, abstractmethod

import ayon_api
import six

from ayon_core.style import get_default_entity_icon_color
from ayon_core.lib import CacheItem, NestedCacheItem

PROJECTS_MODEL_SENDER = "projects.model"


@six.add_metaclass(ABCMeta)
class AbstractHierarchyController:
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
        state (Literal["not_started", "in_progress", "done", "blocked"]):
            Status state.

    """
    def __init__(self, name, color, short, icon, state):
        self.name = name
        self.color = color
        self.short = short
        self.icon = icon
        self.state = state

    def to_data(self):
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


class ProjectItem:
    """Item representing folder entity on a server.

    Folder can be a child of another folder or a project.

    Args:
        name (str): Project name.
        active (Union[str, None]): Parent folder id. If 'None' then project
            is parent.
    """

    def __init__(self, name, active, is_library, icon=None):
        self.name = name
        self.active = active
        self.is_library = is_library
        if icon is None:
            icon = {
                "type": "awesome-font",
                "name": "fa.book" if is_library else "fa.map",
                "color": get_default_entity_icon_color(),
            }
        self.icon = icon

    @classmethod
    def from_entity(cls, project_entity):
        """Creates folder item from entity.

        Args:
            project_entity (dict[str, Any]): Project entity.

        Returns:
            ProjectItem: Project item.

        """
        return cls(
            project_entity["name"],
            project_entity["active"],
            project_entity["library"],
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


def _get_project_items_from_entitiy(projects):
    """

    Args:
        projects (list[dict[str, Any]]): List of projects.

    Returns:
        ProjectItem: Project item.
    """

    return [
        ProjectItem.from_entity(project)
        for project in projects
    ]


class ProjectsModel(object):
    def __init__(self, controller):
        self._projects_cache = CacheItem(default_factory=list)
        self._project_statuses_cache = NestedCacheItem(
            levels=1, default_factory=list
        )
        self._projects_by_name = NestedCacheItem(
            levels=1, default_factory=list
        )

        self._is_refreshing = False
        self._controller = controller

    def reset(self):
        self._projects_cache.reset()
        self._project_statuses_cache.reset()
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

    def get_project_status_items(self, project_name, sender):
        """Get project status items.

        Args:
            project_name (str): Project name.
            sender (Union[str, None]): Name of sender who asked for items.

        Returns:
            list[StatusItem]: Status items for project.

        """
        statuses_cache = self._project_statuses_cache[project_name]
        if not statuses_cache.is_valid:
            with self._project_statuses_refresh_event_manager(
                sender, project_name
            ):
                project_entity = None
                if project_name:
                    project_entity = self.get_project_entity(project_name)
                statuses = []
                if project_entity:
                    statuses = [
                        StatusItem.from_project_item(status)
                        for status in project_entity["statuses"]
                    ]
                statuses_cache.update_data(statuses)
        return statuses_cache.get_data()

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
    def _project_statuses_refresh_event_manager(self, sender, project_name):
        self._controller.emit_event(
            "projects.statuses.refresh.started",
            {"sender": sender, "project_name": project_name},
            PROJECTS_MODEL_SENDER
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                "projects.statuses.refresh.finished",
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

    def _query_projects(self):
        projects = ayon_api.get_projects(fields=["name", "active", "library"])
        return _get_project_items_from_entitiy(projects)
