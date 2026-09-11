"""Abstract base classes for loader tool."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import typing
from typing import Iterable, Any, Callable

from ayon_core.lib.icon_definitions import (
    IconBase,
    get_icon_def_from_data,
)
from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    deserialize_attr_defs,
    serialize_attr_defs,
)
from ayon_core.tools.common_models import TaskItem, ProjectItem

if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models.settings import TaskSortMode


@dataclass
class RepreItem:
    """Representation item.

    Attributes:
        representation_id (str): Representation id.
        representation_name (str): Representation name.
        representation_icon (IconBase): Representation icon definition.
        product_name (str): Product name.
        folder_label (str): Folder label.
    """

    representation_id: str
    representation_name: str
    representation_icon: IconBase
    product_name: str
    folder_label: str

    def to_data(self) -> dict[str, Any]:
        return dict(
            representation_id=self.representation_id,
            representation_name=self.representation_name,
            representation_icon=self.representation_icon.to_data(),
            product_name=self.product_name,
            folder_label=self.folder_label,
        )

    @classmethod
    def from_data(cls, data) -> RepreItem:
        data["representation_icon"] = get_icon_def_from_data(
            data["representation_icon"]
        )
        return cls(**data)


@dataclass
class ActionItem:
    """Action item that can be triggered.

    Action item is defined for a specific context. To trigger the action
    use 'identifier' and context, it necessary also use 'options'.

    Args:
        identifier (str): Action identifier.
        label (str): Action label.
        group_label (str | None): Group label.
        icon (IconBase | dict[str, Any] | None): Action icon definition.
        tooltip (str | None): Action tooltip.
        order (int): Action order.
        data (dict[str, Any] | None): Additional action data.
        options (list[AbstractAttrDef] | None):
            Action options. Note: 'qargparse' is considered as deprecated.

    """
    identifier: str
    label: str
    group_label: str | None
    icon: IconBase | dict[str, Any] | None
    tooltip: str | None
    order: int
    data: dict[str, Any] | None
    options: list[AbstractAttrDef] | None

    def _options_to_data(self):
        options = self.options
        if not options:
            return options
        if isinstance(options[0], AbstractAttrDef):
            return serialize_attr_defs(options)
        # NOTE: Data conversion is not used by default in loader tool. But for
        #   future development of detached UI tools it would be better to be
        #   prepared for it.
        raise NotImplementedError(
            f"{self.__class__.__name__}.to_data is not implemented."
            " Use Attribute definitions from 'ayon_core.lib'"
            " instead of 'qargparse'."
        )

    def to_data(self) -> dict[str, Any]:
        options = self._options_to_data()
        return dict(
            identifier=self.identifier,
            label=self.label,
            group_label=self.group_label,
            icon=self.icon,
            tooltip=self.tooltip,
            order=self.order,
            data=self.data,
            options=options,
        )

    @classmethod
    def from_data(cls, data) -> "ActionItem":
        options = data["options"]
        if options:
            options = deserialize_attr_defs(options)
        data["options"] = options
        return cls(**data)


class AbstractBrowserController(ABC):
    """Base loader controller abstraction.

    Abstract base class that is required for both frontend and backed.
    """

    @abstractmethod
    def get_window_subtitle(self) -> str | None:
        """Get window subtitle.

        Returns:
            str | None: Window subtitle.

        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all cached data to reload everything.

        Triggers events "controller.reset.started" and
        "controller.reset.finished".
        """

        pass

    @abstractmethod
    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        """Emit event with a certain topic, data and source.

        The event should be sent to both frontend and backend.

        Args:
            topic (str): Event topic name.
            data (dict[str, Any] | None): Event data.
            source (str | None): Event source.

        """
        pass

    @abstractmethod
    def register_event_callback(
        self, topic: str, callback: Callable
    ) -> None:
        """Register callback for an event topic.

        Args:
            topic (str): Event topic name.
            callback (func): Callback triggered when the event is emitted.

        """
        pass

    @abstractmethod
    def get_current_context(self) -> dict[str, str | None]:
        """Current context is a context of the current scene.

        Example output:
            {
                "project_name": "MyProject",
                "folder_id": "0011223344-5566778-99",
                "task_name": "Compositing",
            }

        Returns:
            dict[str, str | None]: Context data.

        """
        pass

    @abstractmethod
    def get_project_items(
        self, sender: str | None = None
    ) -> list[ProjectItem]:
        """Items for all projects available on server.

        Triggers event topics "projects.refresh.started" and
        "projects.refresh.finished" with data:
            {
                "sender": sender
            }

        Notes:
            Filtering of projects is done in UI.

        Args:
            sender (str | None): Sender who requested the items.

        Returns:
            list[ProjectItem]: List of project items.

        """
        pass

    @abstractmethod
    def get_project_entity(
        self, project_name: str | None
    ) -> dict[str, Any] | None:
        """Project entity, served from the shared projects cache.

        Args:
            project_name (str | None): Project name.

        Returns:
            dict[str, Any] | None: Project entity, or None when the
                project was not found.

        """
        pass

    @abstractmethod
    def get_folder_items(
        self,
        project_name: str,
        sender: str | None = None,
    ):
        """Folder items for a project.

        Args:
            project_name (str): Project name.
            sender (str | None): Sender who requested the name.

        Returns:
            dict[str, FolderItem]: Folder items by folder id.

        """
        pass

    @abstractmethod
    def get_task_items(
        self,
        project_name: str,
        folder_ids: Iterable[str],
        sender: str | None = None,
    ) -> list[TaskItem]:
        """Task items for folder ids.

        Args:
            project_name (str): Project name.
            folder_ids (Iterable[str]): Folder ids.
            sender (str | None): Sender who requested the items.

        Returns:
            list[TaskItem]: List of task items.

        """
        pass

    @abstractmethod
    def get_task_type_items(self, project_name, sender=None):
        """Task type items for a project.

        This function may trigger events with topics
        'projects.task_types.refresh.started' and
        'projects.task_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested task type items.

        Returns:
            list[TaskTypeItem]: Task type information.

        """
        pass

    @abstractmethod
    def get_task_sorting_mode(self, project_name: str | None) -> TaskSortMode:
        """Used by tasks widget to define how tasks are sorted.

        Args:
            project_name (str | None): Name of the project.

        Returns:
            TaskSortMode: Task sorting mode.

        """

    @abstractmethod
    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        """Get entity ids for my tasks.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, list[str]]: Folder and task ids.

        """
        pass

    @abstractmethod
    def get_representation_items(
        self, project_name: str, version_ids: Iterable[str]
    ) -> list[RepreItem]:
        """Representation items for version ids.

        Triggers event topics "model.representations.refresh.started" and
        "model.representations.refresh.finished" with data:
            {
                "project_name": project_name,
                "version_ids": version_ids,
                "sender": sender
            }

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            list[RepreItem]: List of representation items.

        """
        pass

    @abstractmethod
    def get_versions_representation_count(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, int]:
        """
        Args:
            project_name (str): Project name.
            version_ids (set[str]): Version ids.

        Returns:
            dict[str, int]: Representation count by version id.

        """
        pass

    @abstractmethod
    def set_selected_project(self, project_name: str) -> None:
        """Set selected project.

        Project selection changed in UI. This is required method
            by ProjectsCombobox.
        """
        pass

    # Load action items
    @abstractmethod
    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        """Action items for versions selection.

        Args:
            project_name (str): Project name.
            entity_ids (set[str]): Entity ids.
            entity_type (str): Entity type.

        Returns:
            list[ActionItem]: List of action items.

        """
        pass

    @abstractmethod
    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: dict[str, Any] | None,
        options: dict[str, Any],
        form_values: dict[str, Any],
    ):
        """Trigger action item.

        Triggers event "load.started" with data:
            {
                "identifier": identifier,
                "id": <Random UUID>,
            }

        And triggers "load.finished" with data:
            {
                "identifier": identifier,
                "id": <Random UUID>,
                "error_info": [...],
            }

        Args:
            identifier (sttr): Plugin identifier.
            project_name (str): Project name.
            selected_ids (set[str]): Selected entity ids.
            selected_entity_type (str): Selected entity type.
            data (dict[str, Any] | None): Additional action item data.
            options (dict[str, Any]): Action option values from UI.
            form_values (dict[str, Any]): Action form values from UI.

        """
        pass

    # NOTE: Methods 'is_loaded_products_supported' and
    #   'is_standard_projects_filter_enabled' are both based on being in host
    #   or not. Maybe we could implement only single method 'is_in_host'?
    @abstractmethod
    def is_loaded_products_supported(self):
        """Is capable to get information about loaded products.

        Returns:
            bool: True if it is supported.

        """
        pass

    @abstractmethod
    def is_standard_projects_filter_enabled(self):
        """Is standard projects filter enabled.

        This is used for filtering out when loader tool is used in a host. In
        that case only current project and library projects should be shown.

        Returns:
            bool: Frontend should filter out non-library projects, except
                current context project.

        """
        pass
