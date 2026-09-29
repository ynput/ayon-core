from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import typing
from typing import Any, Callable

from ayon_core.host import PublishedWorkfileInfo

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy

    from ayon_core.host import WorkfileInfo
    from ayon_core.tools.common_models import (
        UserItem,
        FolderTypeItem,
        TaskTypeItem,
        TaskSortMode,
        FolderItem,
        TaskItem,
    )


@dataclass
class WorkareaFilepathResult:
    """Result of workarea file formatting.

    Args:
        root (str): Root path of workarea.
        filename (str): Filename.
        exists (bool): True if file exists.
        filepath (str): Filepath. If not provided it will be constructed
            from root and filename.

    """
    root: str
    filename: str
    exists: bool
    filepath: str = ""

    def __post_init__(self) -> None:
        if not self.filepath and self.root and self.filename:
            self.filepath = os.path.join(self.root, self.filename)

    def to_data(self) -> dict[str, Any]:
        return dict(
            root=self.root,
            filename=self.filename,
            exists=self.exists,
            filepath=self.filepath,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> WorkareaFilepathResult:
        return cls(**data)


@dataclass
class PublishedWorkfileWrap:
    """Wrapper for workfile info that also contains version comment."""
    info: PublishedWorkfileInfo | None = None
    comment: str | None = None

    def to_data(self) -> dict[str, Any]:
        info = None
        if self.info is not None:
            info = self.info.to_data()
        return dict(
            info=info,
            comment=self.comment,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PublishedWorkfileWrap:
        info = data["info"]
        if info is not None:
            info = PublishedWorkfileInfo.from_data(info)
        return cls(info=info, comment=data["comment"])


class AbstractWorkfilesCommon(ABC):
    @abstractmethod
    def is_host_valid(self) -> bool:
        """Host is valid for workfiles tool work.

        Returns:
            bool: True if host is valid.

        """
        pass

    @abstractmethod
    def get_workfile_extensions(self) -> list[str]:
        """Get possible workfile extensions.

        Defined by host implementation.

        Returns:
            list[str]: List of extensions.

        """
        pass

    @abstractmethod
    def is_save_enabled(self) -> bool:
        """Is workfile save enabled.

        Returns:
            bool: True if save is enabled.

        """
        pass

    @abstractmethod
    def set_save_enabled(self, enabled: bool) -> None:
        """Enable or disabled workfile save.

        Args:
            enabled (bool): Enable save workfile when True.

        """
        pass


class AbstractWorkfilesBackend(AbstractWorkfilesCommon):
    # Current context
    @abstractmethod
    def get_host_name(self) -> str:
        """Name of host.

        Returns:
            str: Name of host.

        """
        pass

    @abstractmethod
    def get_current_project_name(self) -> str:
        """Project name from current context of host.

        Returns:
            str: Name of project.

        """
        pass

    @abstractmethod
    def get_current_folder_id(self) -> str | None:
        """Folder id from current context of host.

        Returns:
            str | None: Folder id or None if host does not have
                any context.

        """
        pass

    @abstractmethod
    def get_current_task_name(self) -> str | None:
        """Task name from current context of host.

        Returns:
            str | None: Task name or None if host does not have
                any context.

        """
        pass

    @abstractmethod
    def get_current_workfile(self) -> str | None:
        """Current workfile from current context of host.

        Returns:
            str | None: Path to workfile or None if host does
                not have opened specific file.

        """
        pass

    @abstractmethod
    def get_project_settings(
        self, project_name: str | None
    ) -> dict[str, Any]:
        pass

    @property
    @abstractmethod
    def project_anatomy(self) -> Anatomy:
        """Project anatomy for current project.

        Returns:
            Anatomy: Project anatomy.

        """
        pass

    @property
    @abstractmethod
    def project_settings(self) -> dict[str, Any]:
        """Project settings for current project.

        Returns:
            dict[str, Any]: Project settings.

        """
        pass

    @abstractmethod
    def get_project_entity(self, project_name: str) -> dict[str, Any] | None:
        """Get project entity by name.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, Any] | None: Project entity if is found.

        """
        pass

    @abstractmethod
    def get_folder_entity(
        self, project_name: str, folder_id: str
    ) -> dict[str, Any] | None:
        """Get folder entity by id.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.

        Returns:
            dict[str, Any] | None: Folder entity data.

        """
        pass

    @abstractmethod
    def get_task_entity(
        self, project_name: str, task_id: str
    ) -> dict[str, Any] | None:
        """Get task entity by id.

        Args:
            project_name (str): Project name.
            task_id (str): Task id.

        Returns:
            dict[str, Any] | None: Task entity data.

        """
        pass

    @abstractmethod
    def get_workfile_entities(self, task_id: str) -> list[dict[str, Any]]:
        """Workfile entities for given task.

        Args:
            task_id (str): Task id.

        Returns:
            list[dict[str, Any]]: List of workfile entities.

        """
        pass

    @abstractmethod
    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        """Emit event.

        Args:
            topic (str): Event topic used for callbacks filtering.
            data (dict[str, Any] | None): Event data.
            source (str | None): Event source.

        """
        pass


class AbstractWorkfilesFrontend(AbstractWorkfilesCommon):
    """UI controller abstraction that is used for workfiles tool frontend.

    Abstraction to provide data for UI and to handle UI events.

    Provide access to abstract backend data, like folders and tasks. Cares
    about handling of selection, keep information about current UI selection
    and have ability to tell what selection should UI show.

    Selection is separated into 2 parts, first is what UI elements tell
    about selection, and second is what UI should show as selected.
    """

    @abstractmethod
    def get_window_subtitle(self) -> str | None:
        """Get window subtitle.

        Returns:
            str | None: Window subtitle.

        """

    @abstractmethod
    def register_event_callback(self, topic: str, callback: Callable) -> None:
        """Register event callback.

        Listen for events with given topic.

        Args:
            topic (str): Name of topic.
            callback (Callable): Callback that will be called when event
                is triggered.

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
    def get_user_items_by_name(self) -> dict[str, UserItem]:
        """Get user items available on AYON server.

        Returns:
            dict[str, UserItem]: User items by username.

        """
        pass

    @abstractmethod
    def get_folder_type_items(
        self, project_name: str, sender: str | None = None
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
        self, project_name: str, sender: str | None = None
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
    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, set[str]]:
        """Get entity ids of tasks assigned to the current user for a project.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, set[str]]: Dictionary mapping of folder ids and task ids
                that a user is assigned to.

        """
        pass

    # Selection information
    @abstractmethod
    def get_selected_folder_id(self) -> str | None:
        """Currently selected folder id.

        Returns:
            str | None: Folder id or None if no folder is selected.

        """
        pass

    @abstractmethod
    def set_selected_folder(self, folder_id: str | None) -> None:
        """Change selected folder.

        This deselects currently selected task.

        Args:
            folder_id (str | None): Folder id or None if no folder
                is selected.

        """
        pass

    @abstractmethod
    def get_selected_task_id(self) -> str | None:
        """Currently selected task id.

        Returns:
            str | None: Task id or None if no folder is selected.

        """
        pass

    @abstractmethod
    def get_selected_task_name(self) -> str | None:
        """Currently selected task name.

        Returns:
            str | None: Task name or None if no folder is selected.

        """
        pass

    @abstractmethod
    def set_selected_task(
        self, task_id: str | None, task_name: str | None
    ) -> None:
        """Change selected task.

        Args:
            task_id (str | None): Task id or None if no task
                is selected.
            task_name (str | None): Task name or None if no task
                is selected.

        """
        pass

    @abstractmethod
    def get_selected_workfile_path(self) -> str | None:
        """Currently selected workarea workile.

        Returns:
            str | None: Selected workfile path.

        """
        pass

    @abstractmethod
    def set_selected_workfile_path(
        self,
        rootless_path: str | None,
        path: str | None,
        workfile_entity_id: str | None,
    ) -> None:
        """Change selected workfile path.

        Args:
            rootless_path (str | None): Selected workfile rootless path.
            path (str | None): Selected workfile path.
            workfile_entity_id (str | None): Workfile entity id.

        """
        pass

    @abstractmethod
    def get_selected_representation_id(self) -> str | None:
        """Currently selected workfile representation id.

        Returns:
            str | None: Representation id or None if no representation
                is selected.

        """
        pass

    @abstractmethod
    def set_selected_representation_id(
        self, representation_id: str | None
    ) -> None:
        """Change selected representation.

        Args:
            representation_id (str | None): Selected workfile
                representation id.

        """
        pass

    def get_selected_context(self) -> dict[str, str | None]:
        """Obtain selected context.

        Returns:
            dict[str, str | None]: Selected context.

        """
        return {
            "folder_id": self.get_selected_folder_id(),
            "task_id": self.get_selected_task_id(),
            "task_name": self.get_selected_task_name(),
            "workfile_path": self.get_selected_workfile_path(),
            "representation_id": self.get_selected_representation_id(),
        }

    # Expected selection
    # - expected selection is used to restore selection after refresh
    #   or when current context should be used
    @abstractmethod
    def set_expected_selection(
        self,
        folder_id: str | None,
        task_name: str | None,
        workfile_name: str | None = None,
        representation_id: str | None = None
    ) -> None:
        """Define what should be selected in UI.

        Expected selection provide a way to define/change selection of
        sequential UI elements. For example, if folder and task should be
        selected a task element should wait until folder element has selected
        folder.

        Triggers 'expected_selection.changed' event.

        Args:
            folder_id (str | None): Folder id.
            task_name (str | None): Task name.
            workfile_name (str | None): Workfile name. Used for workarea
                files UI element.
            representation_id (str | None): Representation id. Used for
                published filed UI element.

        """
        pass

    @abstractmethod
    def get_expected_selection_data(self) -> dict[str, Any]:
        """Data of expected selection.

        TODOs:
            Return defined object instead of dict.

        Returns:
            dict[str, Any]: Expected selection data.

        """
        pass

    @abstractmethod
    def expected_folder_selected(self, folder_id: str) -> None:
        """Expected folder was selected in UI.

        Args:
            folder_id (str): Folder id which was selected.

        """
        pass

    @abstractmethod
    def expected_task_selected(
        self, folder_id: str, task_name: str
    ) -> None:
        """Expected task was selected in UI.

        Args:
            folder_id (str): Folder id under which task is.
            task_name (str): Task name which was selected.

        """
        pass

    @abstractmethod
    def expected_representation_selected(
        self, folder_id: str, task_name: str, representation_id: str
    ) -> None:
        """Expected representation was selected in UI.

        Args:
            folder_id (str): Folder id under which representation is.
            task_name (str): Task name under which representation is.
            representation_id (str): Representation id which was selected.

        """
        pass

    @abstractmethod
    def expected_workfile_selected(
        self, folder_id: str, task_name: str, workfile_name: str
    ) -> None:
        """Expected workfile was selected in UI.

        Args:
            folder_id (str): Folder id under which workfile is.
            task_name (str): Task name under which workfile is.
            workfile_name (str): Workfile filename which was selected.

        """
        pass

    @abstractmethod
    def go_to_current_context(self) -> None:
        """Set expected selection to current context."""

        pass

    # Model functions
    @abstractmethod
    def get_folder_items(
        self, project_name: str, sender: str | None = None
    ) -> dict[str, FolderItem]:
        """Folder items to visualize project hierarchy.

        This function may trigger events 'folders.refresh.started' and
        'folders.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of folder items in UI elements.

        Args:
            project_name (str): Project name for which are folders requested.
            sender (str | None): Who requested folder items.

        Returns:
            dict[str, FolderItem]: Minimum possible information needed
                for visualisation of folder hierarchy.

        """
        pass

    @abstractmethod
    def get_task_items(
        self,
        project_name: str,
        folder_id: str,
        sender: str | None = None,
    ) -> list[TaskItem]:
        """Task items.

        This function may trigger events 'tasks.refresh.started' and
        'tasks.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of task items in UI elements.

        Args:
            project_name (str): Project name for which are tasks requested.
            folder_id (str): Folder ID for which are tasks requested.
            sender (str | None): Who requested folder items.

        Returns:
            list[TaskItem]: Minimum possible information needed
                for visualisation of tasks.

        """
        pass

    @abstractmethod
    def has_unsaved_changes(self) -> bool | None:
        """Has host unsaved change in currently running session.

        Returns:
            bool | None: Has unsaved changes or None if unknown.

        """
        pass

    @abstractmethod
    def get_workarea_dir_by_context(
        self, folder_id: str, task_id: str
    ) -> str | None:
        """Get workarea directory by context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            str | None: Workarea directory.

        """
        pass

    @abstractmethod
    def get_workarea_file_items(
        self,
        folder_id: str,
        task_name: str,
        sender: str | None = None,
    ) -> list[WorkfileInfo]:
        """Get workarea file items.

        Args:
            folder_id (str): Folder id.
            task_name (str): Task name.
            sender (str | None): Who requested workarea file items.

        Returns:
            list[WorkfileInfo]: List of workarea file items.

        """
        pass

    @abstractmethod
    def get_workarea_save_as_data(
        self, folder_id: str, task_id: str
    ) -> dict[str, Any]:
        """Prepare data for Save As operation.

        Todos:
            Return defined object instead of dict.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            dict[str, Any]: Data for Save As operation.

        """
        pass

    @abstractmethod
    def fill_workarea_filepath(
        self,
        folder_id: str,
        task_id: str,
        extension: str,
        use_last_version: bool,
        version: int,
        comment: str | None,
    ):
        """Calculate workfile path for passed context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            extension (str): File extension.
            use_last_version (bool): Use last version.
            version (int): Version used if 'use_last_version' if 'False'.
            comment (str | None): User's comment (subversion).

        Returns:
            WorkareaFilepathResult: Result of the operation.

        """
        pass

    @abstractmethod
    def get_published_file_items(
        self, folder_id: str, task_id: str
    ) -> list[PublishedWorkfileInfo]:
        """Get published file items.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            list[PublishedWorkfileInfo]: List of published file items.

        """
        pass

    @abstractmethod
    def get_published_workfile_info(
        self,
        folder_id: str | None,
        representation_id: str | None,
    ) -> PublishedWorkfileWrap:
        """Get published workfile info by representation ID.

        Args:
            folder_id (str | None): Folder id.
            representation_id (str | None): Representation id.

        Returns:
            PublishedWorkfileWrap: Published workfile info or None
                if not found.

        """
        pass

    @abstractmethod
    def get_workfile_info(
        self, folder_id: str, task_id: str, rootless_path: str
    ) -> WorkfileInfo | None:
        """Workfile info from database.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            rootless_path (str): Workfile path.

        Returns:
            WorkfileInfo | None: Workfile info or None if was passed
                invalid context.

        """
        pass

    @abstractmethod
    def save_workfile_info(
        self,
        task_id: str,
        rootless_path: str,
        version: int | None = None,
        comment: str | None = None,
        description: str | None = None,
    ) -> None:
        """Save workfile info to database.

        At this moment the only information which can be saved about
            workfile is 'description'.

        If value of 'version', 'comment' or 'description' is 'None' it is not
            added/updated to entity.

        Args:
            task_id (str): Task id.
            rootless_path (str): Rootless workfile path.
            version (int | None): Version of workfile.
            comment (str | None): User's comment (subversion).
            description (str | None): Workfile description.

        """
        pass

    # General commands
    @abstractmethod
    def reset(self) -> None:
        """Reset everything, models, ui etc.

        Triggers 'controller.reset.started' event at the beginning and
        'controller.reset.finished' at the end.

        """
        pass

    # Controller actions
    @abstractmethod
    def open_workfile(
        self, folder_id: str, task_id: str, filepath: str
    ) -> None:
        """Open a workfile for context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            filepath (str): Workfile path.

        """
        pass

    @abstractmethod
    def save_current_workfile(self) -> None:
        """Save state of current workfile."""

        pass

    @abstractmethod
    def save_as_workfile(
        self,
        folder_id: str,
        task_id: str,
        rootless_workdir: str,
        workdir: str,
        filename: str,
        version: int,
        comment: str | None,
        description: str | None,
    ) -> None:
        """Save current state of workfile to workarea.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            rootless_workdir (str): Workarea directory.
            workdir (str): Workarea directory.
            filename (str): Workarea filename.
            version (int): Version of workfile.
            comment (str | None): User's comment (subversion).
            description (str | None): Workfile description.

        """
        pass

    @abstractmethod
    def copy_workfile_representation(
        self,
        representation_id: str,
        representation_filepath: str,
        folder_id: str,
        task_id: str,
        workdir: str,
        filename: str,
        rootless_workdir: str,
        version: int,
        comment: str | None,
        description: str | None,
    ) -> None:
        """Action to copy published workfile representation to workarea.

        Triggers 'copy_representation.started' event on start and
        'copy_representation.finished' event with '{"failed": bool}'.

        Args:
            representation_id (str): Representation id.
            representation_filepath (str): Path to representation file.
            folder_id (str): Folder id.
            task_id (str): Task id.
            workdir (str): Workarea directory.
            filename (str): Workarea filename.
            rootless_workdir (str): Rootless workdir.
            version (int): Workfile version.
            comment (str | None): User's comment (subversion).
            description (str | None): Description note.

        """
        pass

    @abstractmethod
    def duplicate_workfile(
        self,
        folder_id: str,
        task_id: str,
        src_filepath: str,
        rootless_workdir: str,
        workdir: str,
        filename: str,
        version: int,
        comment: str | None,
        description: str | None,
    ) -> None:
        """Duplicate workfile.

        Workfiles is not opened when done.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            src_filepath (str): Source workfile path.
            rootless_workdir (str): Rootless workdir.
            workdir (str): Destination workdir.
            filename (str): Destination filename.
            version (int): Workfile version.
            comment (str): User's comment (subversion).
            description (str): Workfile description.
        """
        pass
