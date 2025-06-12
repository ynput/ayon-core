from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any

from ayon_core.tools.common_models import (
    ProjectItem,
    FolderItem,
    FolderTypeItem,
    TaskItem,
    TaskTypeItem,
)


@dataclass
class WebactionContext:
    """Context used for methods related to webactions."""
    identifier: str
    project_name: str
    folder_id: str
    task_id: str
    addon_name: str
    addon_version: str


@dataclass
class ActionItem:
    """Item representing single action to trigger.

    Attributes:
        action_type (Literal["webaction", "local"]): Type of action.
        identifier (str): Unique identifier of action item.
        order (int): Action ordering.
        label (str): Action label.
        variant_label (Union[str, None]): Variant label, full label is
            concatenated with space. Actions are grouped under single
            action if it has same 'label' and have set 'variant_label'.
        full_label (str): Full label, if not set it is generated
            from 'label' and 'variant_label'.
        icon (dict[str, str]): Icon definition.
        addon_name (Optional[str]): Addon name.
        addon_version (Optional[str]): Addon version.
        config_fields (list[dict]): Config fields for webaction.

    """
    action_type: str
    identifier: str
    order: int
    label: str
    variant_label: Optional[str]
    full_label: str
    icon: Optional[dict[str, str]]
    config_fields: list[dict]
    addon_name: Optional[str] = None
    addon_version: Optional[str] = None

    @staticmethod
    def calculate_full_label(label: str, variant_label: Optional[str]) -> str:
        """Calculate full label from label and variant_label."""
        if variant_label:
            return " ".join([label, variant_label])
        return label


class AbstractLauncherCommon(ABC):
    @abstractmethod
    def register_event_callback(self, topic, callback):
        """Register event callback.

        Listen for events with given topic.

        Args:
            topic (str): Name of topic.
            callback (Callable): Callback that will be called when event
                is triggered.
        """

        pass


class AbstractLauncherBackend(AbstractLauncherCommon):
    @abstractmethod
    def emit_event(self, topic, data=None, source=None):
        """Emit event.

        Args:
            topic (str): Event topic used for callbacks filtering.
            data (Optional[dict[str, Any]]): Event data.
            source (Optional[str]): Event source.
        """

        pass

    @abstractmethod
    def get_project_settings(self, project_name):
        """Project settings for current project.

        Args:
            project_name (Union[str, None]): Project name.

        Returns:
            dict[str, Any]: Project settings.
        """

        pass

    @abstractmethod
    def get_project_entity(self, project_name):
        """Get project entity by name.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, Any]: Project entity data.
        """

        pass

    @abstractmethod
    def get_folder_entity(self, project_name, folder_id):
        """Get folder entity by id.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.

        Returns:
            dict[str, Any]: Folder entity data.
        """

        pass

    @abstractmethod
    def get_task_entity(self, project_name, task_id):
        """Get task entity by id.

        Args:
            project_name (str): Project name.
            task_id (str): Task id.

        Returns:
            dict[str, Any]: Task entity data.
        """

        pass


class AbstractLauncherFrontEnd(AbstractLauncherCommon):
    # Entity items for UI
    @abstractmethod
    def get_project_items(
        self, sender: Optional[str] = None
    ) -> list[ProjectItem]:
        """Project items for all projects.

        This function may trigger events 'projects.refresh.started' and
        'projects.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of project items in UI elements.

        Args:
            sender (str): Who requested folder items.

        Returns:
            list[ProjectItem]: Minimum possible information needed
                for visualisation of folder hierarchy.

        """
        pass

    @abstractmethod
    def get_folder_type_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> list[FolderTypeItem]:
        """Folder type items for a project.

        This function may trigger events with topics
        'projects.folder_types.refresh.started' and
        'projects.folder_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested folder type items.

        Returns:
            list[FolderTypeItem]: Folder type information.

        """
        pass

    @abstractmethod
    def get_task_type_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> list[TaskTypeItem]:
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
    def get_folder_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> list[FolderItem]:
        """Folder items to visualize project hierarchy.

        This function may trigger events 'folders.refresh.started' and
        'folders.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of folder items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested folder items.

        Returns:
            list[FolderItem]: Minimum possible information needed
                for visualisation of folder hierarchy.

        """
        pass

    @abstractmethod
    def get_task_items(
        self, project_name: str, folder_id: str, sender: Optional[str] = None
    ) -> list[TaskItem]:
        """Task items.

        This function may trigger events 'tasks.refresh.started' and
        'tasks.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of task items in UI elements.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder ID for which are tasks requested.
            sender (str): Who requested folder items.

        Returns:
            list[TaskItem]: Minimum possible information needed
                for visualisation of tasks.

        """
        pass

    @abstractmethod
    def get_selected_project_name(self) -> Optional[str]:
        """Selected project name.

        Returns:
            Union[str, None]: Selected project name.

        """
        pass

    @abstractmethod
    def get_selected_folder_id(self) -> Optional[str]:
        """Selected folder id.

        Returns:
            Union[str, None]: Selected folder id.

        """
        pass

    @abstractmethod
    def get_selected_task_id(self) -> Optional[str]:
        """Selected task id.

        Returns:
            Union[str, None]: Selected task id.

        """
        pass

    @abstractmethod
    def get_selected_task_name(self) -> Optional[str]:
        """Selected task name.

        Returns:
            Union[str, None]: Selected task name.

        """
        pass

    @abstractmethod
    def get_selected_context(self) -> dict[str, Optional[str]]:
        """Get whole selected context.

        Example:
            {
                "project_name": self.get_selected_project_name(),
                "folder_id": self.get_selected_folder_id(),
                "task_id": self.get_selected_task_id(),
                "task_name": self.get_selected_task_name(),
            }

        Returns:
            dict[str, Union[str, None]]: Selected context.

        """
        pass

    @abstractmethod
    def set_selected_project(self, project_name: Optional[str]):
        """Change selected folder.

        Args:
            project_name (Union[str, None]): Project nameor None if no project
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_folder(self, folder_id: Optional[str]):
        """Change selected folder.

        Args:
            folder_id (Union[str, None]): Folder id or None if no folder
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_task(
        self, task_id: Optional[str], task_name: Optional[str]
    ):
        """Change selected task.

        Args:
            task_id (Union[str, None]): Task id or None if no task
                is selected.
            task_name (Union[str, None]): Task name or None if no task
                is selected.

        """
        pass

    # Actions
    @abstractmethod
    def get_action_items(
        self,
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
    ) -> list[ActionItem]:
        """Get action items for given context.

        Args:
            project_name (Union[str, None]): Project name.
            folder_id (Union[str, None]): Folder id.
            task_id (Union[str, None]): Task id.

        Returns:
            list[ActionItem]: List of action items that should be shown
                for given context.

        """
        pass

    @abstractmethod
    def trigger_action(
        self,
        action_id: str,
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
    ):
        """Trigger action on given context.

        Args:
            action_id (str): Action identifier.
            project_name (Union[str, None]): Project name.
            folder_id (Union[str, None]): Folder id.
            task_id (Union[str, None]): Task id.

        """
        pass

    @abstractmethod
    def trigger_webaction(
        self,
        context: WebactionContext,
        action_label: str,
        form_data: Optional[dict[str, Any]] = None,
    ):
        """Trigger action on the given context.

        Args:
            context (WebactionContext): Webaction context.
            action_label (str): Action label.
            form_data (Optional[dict[str, Any]]): Form values of action.

        """
        pass

    @abstractmethod
    def get_action_config_values(
        self, context: WebactionContext
    ) -> dict[str, Any]:
        """Get action config values.

        Args:
            context (WebactionContext): Webaction context.

        Returns:
            dict[str, Any]: Action config values.

        """
        pass

    @abstractmethod
    def set_action_config_values(
        self,
        context: WebactionContext,
        values: dict[str, Any],
    ):
        """Set action config values.

        Args:
            context (WebactionContext): Webaction context.
            values (dict[str, Any]): Action config values.

        """
        pass

    @abstractmethod
    def refresh(self):
        """Refresh everything, models, ui etc.

        Triggers 'controller.refresh.started' event at the beginning and
        'controller.refresh.finished' at the end.
        """

        pass

    @abstractmethod
    def refresh_actions(self):
        """Refresh actions and all related data.

        Triggers 'controller.refresh.actions.started' event at the beginning
        and 'controller.refresh.actions.finished' at the end.
        """
        pass

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
