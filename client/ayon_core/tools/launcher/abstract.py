from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import typing
from typing import Literal, Optional, Any

from ayon_core.addon import AddonsManager
from ayon_core.tools.common_models import (
    ProjectItem,
    FolderItem,
    FolderTypeItem,
    TaskItem,
    TaskTypeItem,
)

if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models.settings import TaskSortMode

# How many recent actions are kept. Favorited entries are pinned and do
# not count towards it.
RECENT_ACTIONS_MAX = 10


@dataclass
class WebactionContext:
    """Context used for methods related to webactions."""
    identifier: str
    project_name: str
    folder_id: str
    task_id: str
    workfile_id: str
    addon_name: str
    addon_version: str


@dataclass
class ActionItem:
    """Item representing single action to trigger.

    Attributes:
        action_type (Literal["webaction", "local"]): Type of action.
        identifier (str): Unique identifier of action item.
        order (int): Action ordering.
        suborder (int): Internal ordering used for webactions order.
        label (str): Action label.
        variant_label (Optional[str]): Variant label, full label is
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
    suborder: int
    label: str
    variant_label: Optional[str]
    full_label: str
    icon: Optional[dict[str, str]]
    config_fields: list[dict]
    addon_name: Optional[str] = None
    addon_version: Optional[str] = None


@dataclass
class WorkfileItem:
    workfile_id: str
    filename: str
    exists: bool
    host_name: str | None
    icon: str | None
    version: int | None
    updated_at_time: float | None
    file_size: int | None = None


@dataclass
class ContextLabels:
    """Human readable names of a launcher context.

    Attributes:
        folder_path (Optional[str]): Folder path.
        task_name (Optional[str]): Task name.
        workfile_name (Optional[str]): Workfile filename.

    """

    folder_path: Optional[str] = None
    task_name: Optional[str] = None
    workfile_name: Optional[str] = None


@dataclass
class RecentActionItem:
    """A triggered action, the context it ran in and how to display it.

    Stored as is in current user's data on the AYON server, so that showing
    the history costs a single request and never has to resolve entities or
    actions first.

    The display attributes ('label', 'icon' and the context names) are a
    snapshot taken when the action was triggered. They are only used to draw
    the row - whether the action can still run is decided from the ids when
    it is actually triggered.

    No addon version is kept. An entry points at an action of an addon, and
    which version of that addon provides it is whatever the enabled bundle
    says at the time it is triggered - a version stored months ago would
    only be misleading after a studio updates its bundle.

    Attributes:
        record_id (str): Unique identifier for this history entry (UUID hex).
        action_type (Literal["local", "webaction"]): Type of action.
        identifier (str): Action identifier used to re-trigger the action.
        timestamp (float): Unix timestamp of when the action was triggered.
        project_name (Optional[str]): Project name at trigger time.
        folder_id (Optional[str]): Folder id at trigger time.
        task_id (Optional[str]): Task id at trigger time.
        workfile_id (Optional[str]): Workfile id at trigger time.
        addon_name (Optional[str]): Addon name (webactions only).
        label (str): Full label of the action as it was when triggered.
        folder_path (Optional[str]): Folder path at trigger time.
        task_name (Optional[str]): Task name at trigger time.
        workfile_name (Optional[str]): Workfile filename at trigger time.
        icon (Optional[dict[str, str]]): Icon definition of the action, same
            format as :attr:`ActionItem.icon`.
        favorite (bool): Entry is pinned to the top of the history and is
            never pushed out of it by newer actions.

    """

    record_id: str
    action_type: Literal["local", "webaction"]
    identifier: str
    timestamp: float
    project_name: Optional[str] = None
    folder_id: Optional[str] = None
    task_id: Optional[str] = None
    workfile_id: Optional[str] = None
    addon_name: Optional[str] = None
    label: str = ""
    folder_path: Optional[str] = None
    task_name: Optional[str] = None
    workfile_name: Optional[str] = None
    icon: Optional[dict[str, str]] = None
    favorite: bool = False


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
    def get_addons_manager(self) -> AddonsManager:
        pass

    @abstractmethod
    def get_project_settings(self, project_name):
        """Project settings for current project.

        Args:
            project_name (Optional[str]): Project name.

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
    def get_context_labels(
        self,
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
        workfile_id: Optional[str],
    ) -> ContextLabels:
        """Get human readable names of a context.

        Meant to label a context that is currently in use, so it is served
        from what the launcher already has loaded whenever possible.

        Args:
            project_name (Optional[str]): Project name.
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.
            workfile_id (Optional[str]): Workfile id.

        Returns:
            ContextLabels: Names of the context entities.

        """
        pass

    @abstractmethod
    def get_action_item(
        self,
        action_type: str,
        identifier: str,
        addon_name: Optional[str],
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
        workfile_id: Optional[str],
    ) -> Optional[ActionItem]:
        """Get a single, already known action available in a context.

        The action is matched by its identifier and the addon providing it.
        The returned item is the action as the currently enabled bundle
        provides it, including the addon version to use for it.

        Args:
            action_type (str): Type of action, 'local' or 'webaction'.
            identifier (str): Action identifier.
            addon_name (Optional[str]): Addon name (webactions only).
            project_name (Optional[str]): Project name.
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.
            workfile_id (Optional[str]): Workfile id.

        Returns:
            Optional[ActionItem]: Matching action item, 'None' when the
                action does not exist or is not compatible with the context.

        """
        pass

    @abstractmethod
    def get_local_action_label_icon(
        self, identifier: str
    ) -> Optional[tuple[str, Optional[dict[str, str]]]]:
        """Get how a local action is labelled right now.

        Reads the discovered action directly, so it needs no project
        context and issues no requests.

        Args:
            identifier (str): Action identifier.

        Returns:
            Optional[tuple[str, Optional[dict[str, str]]]]: Full label and
                icon definition, 'None' if no such action exists.

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
    @abstractmethod
    def get_task_sorting_mode(self, project_name: str | None) -> TaskSortMode:
        """Used by tasks widget to define how tasks are sorted.

        Args:
            project_name (str | None): Name of the project.

        Returns:
            TaskSortMode: Task sorting mode.

        """

    @abstractmethod
    def get_grouped_host_names(self) -> list[str | None]:
        """Get list of host names that will group workfiles."""

    @abstractmethod
    def set_grouped_host_names(self, host_names: list[str | None]):
        """Set list of host names that will group workfiles."""

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
            Optional[str]: Selected project name.

        """
        pass

    @abstractmethod
    def get_selected_folder_id(self) -> Optional[str]:
        """Selected folder id.

        Returns:
            Optional[str]: Selected folder id.

        """
        pass

    @abstractmethod
    def get_selected_task_id(self) -> Optional[str]:
        """Selected task id.

        Returns:
            Optional[str]: Selected task id.

        """
        pass

    @abstractmethod
    def get_selected_task_name(self) -> Optional[str]:
        """Selected task name.

        Returns:
            Optional[str]: Selected task name.

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
            dict[str, Optional[str]]: Selected context.

        """
        pass

    @abstractmethod
    def set_selected_project(self, project_name: Optional[str]):
        """Change selected folder.

        Args:
            project_name (Optional[str]): Project nameor None if no project
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_folder(self, folder_id: Optional[str]):
        """Change selected folder.

        Args:
            folder_id (Optional[str]): Folder id or None if no folder
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_task(
        self, task_id: Optional[str], task_name: Optional[str]
    ):
        """Change selected task.

        Args:
            task_id (Optional[str]): Task id or None if no task
                is selected.
            task_name (Optional[str]): Task name or None if no task
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_workfile(self, workfile_id: Optional[str]):
        """Change selected workfile.

        Args:
            workfile_id (Optional[str]): Workfile id or None.

        """
        pass

    # Actions
    @abstractmethod
    def get_action_items(
        self,
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
        workfile_id: Optional[str],
    ) -> list[ActionItem]:
        """Get action items for given context.

        Args:
            project_name (Optional[str]): Project name.
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.
            workfile_id (Optional[str]): Workfile id.

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
        workfile_id: Optional[str],
    ):
        """Trigger action on given context.

        Args:
            action_id (str): Action identifier.
            project_name (Optional[str]): Project name.
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.
            workfile_id (Optional[str]): Task id.

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

    @abstractmethod
    def get_workfile_items(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        """Get workfile items for a given context.

        Args:
            project_name (Optional[str]): Project name.
            task_id (Optional[str]): Task id.

        Returns:
            list[WorkfileItem]: List of workfile items.

        """
        pass

    # Recent actions
    @abstractmethod
    def get_recent_action_items(self) -> list[RecentActionItem]:
        """Get the recent actions loaded by the last refresh.

        Does not query anything, so it is safe to call while painting. An
        empty list is returned until the first refresh finished.

        Favorited items come first, then the rest. Both groups are ordered
        from most to least recently triggered.

        Returns:
            list[RecentActionItem]: Recent action history items.

        """
        pass

    @abstractmethod
    def set_recent_action_favorite(self, record_id: str, favorite: bool):
        """Pin a history entry to the top of the list, or unpin it.

        A favorited entry stays in the history until it is unfavorited or
        removed, newer actions never push it out.

        Args:
            record_id (str): The :attr:`RecentActionItem.record_id` of the
                entry to change.
            favorite (bool): Entry should be favorited.

        """
        pass

    @abstractmethod
    def remove_recent_action(self, record_id: str):
        """Drop an entry from the history.

        Args:
            record_id (str): The :attr:`RecentActionItem.record_id` of the
                entry to remove.

        """
        pass

    @abstractmethod
    def are_recent_action_items_loaded(self) -> bool:
        """Whether the history was loaded at least once.

        Lets the UI tell "nothing was loaded yet" apart from "there is no
        history", so it can show the right message.

        Returns:
            bool: History is loaded.

        """
        pass

    @abstractmethod
    def refresh_recent_action_items(self):
        """Load the recent actions history.

        Single request, everything needed to display the history is stored
        with it. Blocks, so it is expected to be called from a worker
        thread, after which :meth:`get_recent_action_items` returns the
        loaded items.

        """
        pass

    @abstractmethod
    def trigger_recent_action(self, record_id: str):
        """Re-trigger an action from history without changing current context.

        The action is executed against the context that was stored when it was
        originally triggered, leaving the launcher's current selection
        unchanged.

        Args:
            record_id (str): The :attr:`RecentActionItem.record_id` of the
                history entry to replay.

        """
        pass

    @abstractmethod
    def apply_recent_action_context(self, record_id: str):
        """Apply context stored in a recent action to the current selection.

        Changes the launcher's project/folder/task/workfile selection to match
        the context that was active when *record_id* was originally triggered.
        This is the "Locate" affordance – it does **not** re-run the action.

        Args:
            record_id (str): The :attr:`RecentActionItem.record_id` of the
                history entry whose context should be restored.

        """
        pass
