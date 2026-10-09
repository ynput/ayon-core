"""API for actions of workfiles tool.

Even though the api is meant for the workfiles tool, the api should be
    possible to use in a standalone way out of the workfiles tool.

To add actions, make sure your addon does inherit from 'IPluginPaths' and
    implements 'get_workfile_action_plugin_paths' which returns paths to
    python files with workfile actions.

The plugin is used to collect available actions for the given selection and
    to execute them. Selection is defined with 'WorkfileActionSelection'
    object. The selection knows which area is shown ('workarea' or
    'published'), in which context and which workfile is selected, if any.
    It also contains a cache of entities, project anatomy and settings that
    are fetched only if they were not passed in by the tool.

Implementing 'get_action_items' allows the plugin to define what actions
    are shown and available for the selection. One plugin can return
    multiple action items, the 'data' attribute of an item can be used to
    tell them apart on execution (they have to be json-serializable).

The action is triggered by calling the 'execute_action' method. Which takes
    the selection, the additional data from the action item and form values
    from the form if any.

Using 'WorkfileActionResult' as the output of 'execute_action' can trigger
    to show a message in UI, to show an additional form ('ActionForm') which
    would retrigger the action with the values from the form on submitting,
    to refresh the tool or to redirect the tool to a different context.

    The plugin also has helper methods 'redirect', 'request_refresh',
    'request_open_workfile', 'request_duplicate_workfile' and
    'request_close' that can be called any time during 'execute_action'
    without the need to return a result object.

It is also recommended that the plugin does override the 'identifier'
    attribute. The identifier has to be unique across all plugins.
    Class name is used by default.

Settings of a plugin are looked for in
    '<settings_category>/workfile_actions/<class name>' of project settings.
    All values are set as attributes on the plugin, so 'enabled' can be used
    to disable the plugin.

Important:
    Method 'get_action_items' can be called out of the main thread, so the
        UI is not blocked while the actions are collected. Do not call
        DCC api that is not thread-safe there. Use information from
        the selection instead. Method 'execute_action' is always called in
        the main thread.

NOTE: It is possible to trigger 'execute_action' without ever calling
    'get_action_items', that can be handy in automations.

The whole logic is wrapped into 'WorkfileActionsContext'. It takes care of
    the discovery of plugins and wraps the collection and execution of
    action items. Method 'execute_action' on context also requires plugin
    identifier.

"""
from __future__ import annotations

import os
import copy
import logging
import threading
from abc import ABC, abstractmethod
import typing
from typing import Optional, Any
from dataclasses import dataclass

import ayon_api

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import StrEnum, Logger
from ayon_core.lib.attribute_definitions import UILabelDef, BoolDef
from ayon_core.lib.icon_definitions import IconBase
from ayon_core.host import AbstractHost, IWorkfileHost
from ayon_core.addon import AddonsManager, IPluginPaths
from ayon_core.settings import get_studio_settings, get_project_settings
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.plugin_discover import discover_plugins

from .structures import ActionForm

if typing.TYPE_CHECKING:
    from typing import Union

    from ayon_core.host import WorkfileInfo, PublishedWorkfileInfo

    DataBaseType = Union[str, int, float, bool]
    DataType = dict[str, Union[DataBaseType, list[DataBaseType]]]

_PLACEHOLDER = object()
SAVE_CHANGES_FORM_KEY = "save_current_workfile"


class WorkfileAreaType(StrEnum):
    """Area of workfiles the selection is related to."""
    workarea = "workarea"
    published = "published"


class WorkfileActionSelection:
    """Selection in workfiles tool for workfile actions.

    Selection tells action plugins which area is shown, what context is
        selected and which workfile is selected. Workfile does not have to
        be selected, in that case the action is related to the area itself,
        e.g. to the work directory of the task.

    Contains entity cache which can be used to get entities related to
        the selection. Entities, project anatomy and project settings are
        fetched on demand if were not passed in.

    Args:
        project_name (str): Project name.
        area (WorkfileAreaType): Area the selection comes from.
        folder_id (Optional[str]): Selected folder id.
        task_id (Optional[str]): Selected task id.
        filepath (Optional[str]): Path to the selected workfile.
        rootless_path (Optional[str]): Rootless path to the selected
            workfile. Available only for workarea workfiles.
        workfile_entity_id (Optional[str]): Id of workfile entity of the
            selected workarea workfile.
        representation_id (Optional[str]): Id of selected published workfile
            representation.
        workdir (Optional[str]): Work directory of the selected task.
        workfile_info (Union[WorkfileInfo, PublishedWorkfileInfo, None]):
            Information about the selected workfile from the host
            integration.
        host_name (Optional[str]): Host name used to calculate the work
            directory.
        project_entity (Optional[dict[str, Any]]): Prepared project entity.
        folder_entity (Optional[dict[str, Any]]): Prepared folder entity.
        task_entity (Optional[dict[str, Any]]): Prepared task entity.
        workfile_entity (Optional[dict[str, Any]]): Prepared workfile
            entity.
        representation_entity (Optional[dict[str, Any]]): Prepared
            representation entity.
        version_entity (Optional[dict[str, Any]]): Prepared version entity.
        project_anatomy (Optional[Anatomy]): Prepared project anatomy.
        project_settings (Optional[dict[str, Any]]): Prepared project
            settings.

    """
    def __init__(
        self,
        project_name: str,
        area: WorkfileAreaType,
        *,
        folder_id: Optional[str] = None,
        task_id: Optional[str] = None,
        filepath: Optional[str] = None,
        rootless_path: Optional[str] = None,
        workfile_entity_id: Optional[str] = None,
        representation_id: Optional[str] = None,
        workdir: Optional[str] = None,
        workfile_info: Union[WorkfileInfo, PublishedWorkfileInfo, None] = None,
        host_name: Optional[str] = None,
        project_entity: Optional[dict[str, Any]] = None,
        folder_entity: Optional[dict[str, Any]] = None,
        task_entity: Optional[dict[str, Any]] = None,
        workfile_entity: Optional[dict[str, Any]] = None,
        representation_entity: Optional[dict[str, Any]] = None,
        version_entity: Optional[dict[str, Any]] = None,
        project_anatomy: Optional[Anatomy] = None,
        project_settings: Optional[dict[str, Any]] = None,
    ) -> None:
        self._project_name = project_name
        self._area = WorkfileAreaType(area)
        self._folder_id = folder_id
        self._task_id = task_id
        self._filepath = filepath
        self._rootless_path = rootless_path
        self._workfile_entity_id = workfile_entity_id
        self._representation_id = representation_id
        self._workfile_info = workfile_info
        self._host_name = host_name

        # Values that are fetched on demand if were not passed in
        self._workdir = workdir or _PLACEHOLDER
        self._project_entity = project_entity or _PLACEHOLDER
        self._folder_entity = folder_entity or _PLACEHOLDER
        self._task_entity = task_entity or _PLACEHOLDER
        self._workfile_entity = workfile_entity or _PLACEHOLDER
        self._representation_entity = representation_entity or _PLACEHOLDER
        self._version_entity = version_entity or _PLACEHOLDER
        self._project_anatomy = project_anatomy
        self._project_settings = project_settings

    def get_project_name(self) -> str:
        return self._project_name

    def get_area(self) -> WorkfileAreaType:
        return self._area

    def get_folder_id(self) -> Optional[str]:
        return self._folder_id

    def get_task_id(self) -> Optional[str]:
        return self._task_id

    def get_filepath(self) -> Optional[str]:
        return self._filepath

    def get_rootless_path(self) -> Optional[str]:
        return self._rootless_path

    def get_workfile_entity_id(self) -> Optional[str]:
        return self._workfile_entity_id

    def get_representation_id(self) -> Optional[str]:
        return self._representation_id

    def get_workfile_info(
        self
    ) -> Union[WorkfileInfo, PublishedWorkfileInfo, None]:
        """Information about the selected workfile from host integration.

        The information is available only if the tool which created
            the selection has it. Is 'WorkfileInfo' for workarea workfiles
            and 'PublishedWorkfileInfo' for published workfiles.

        """
        return self._workfile_info

    def get_filename(self) -> Optional[str]:
        """Filename of the selected workfile."""
        if not self._filepath:
            return None
        return os.path.basename(self._filepath)

    def get_project_settings(self) -> dict[str, Any]:
        if self._project_settings is None:
            self._project_settings = get_project_settings(self._project_name)
        return copy.deepcopy(self._project_settings)

    def get_project_anatomy(self) -> Anatomy:
        if self._project_anatomy is None:
            self._project_anatomy = Anatomy(
                self._project_name,
                project_entity=self.get_project_entity(),
            )
        return self._project_anatomy

    def get_project_entity(self) -> Optional[dict[str, Any]]:
        if self._project_entity is _PLACEHOLDER:
            self._project_entity = ayon_api.get_project(self._project_name)
        return copy.deepcopy(self._project_entity)

    def get_folder_entity(self) -> Optional[dict[str, Any]]:
        """Selected folder entity.

        Returns:
            Optional[dict[str, Any]]: Folder entity or None if folder is not
                selected.

        """
        if self._folder_entity is _PLACEHOLDER:
            folder_entity = None
            if self._folder_id:
                folder_entity = ayon_api.get_folder_by_id(
                    self._project_name, self._folder_id
                )
            self._folder_entity = folder_entity
        return copy.deepcopy(self._folder_entity)

    def get_task_entity(self) -> Optional[dict[str, Any]]:
        """Selected task entity.

        Returns:
            Optional[dict[str, Any]]: Task entity or None if task is not
                selected.

        """
        if self._task_entity is _PLACEHOLDER:
            task_entity = None
            if self._task_id:
                task_entity = ayon_api.get_task_by_id(
                    self._project_name, self._task_id
                )
            self._task_entity = task_entity
        return copy.deepcopy(self._task_entity)

    def get_workfile_entity(self) -> Optional[dict[str, Any]]:
        """Workfile entity of selected workarea workfile.

        Returns:
            Optional[dict[str, Any]]: Workfile entity or None if workfile is
                not selected or does not have entity in the database.

        """
        if self._workfile_entity is _PLACEHOLDER:
            workfile_entity = None
            if self._workfile_entity_id:
                workfile_entity = ayon_api.get_workfile_info_by_id(
                    self._project_name, self._workfile_entity_id
                )
            self._workfile_entity = workfile_entity
        return copy.deepcopy(self._workfile_entity)

    def get_representation_entity(self) -> Optional[dict[str, Any]]:
        """Representation entity of selected published workfile.

        Returns:
            Optional[dict[str, Any]]: Representation entity or None if
                published workfile is not selected.

        """
        if self._representation_entity is _PLACEHOLDER:
            repre_entity = None
            if self._representation_id:
                repre_entity = ayon_api.get_representation_by_id(
                    self._project_name, self._representation_id
                )
            self._representation_entity = repre_entity
        return copy.deepcopy(self._representation_entity)

    def get_version_entity(self) -> Optional[dict[str, Any]]:
        """Version entity of selected published workfile.

        Returns:
            Optional[dict[str, Any]]: Version entity or None if published
                workfile is not selected.

        """
        if self._version_entity is _PLACEHOLDER:
            version_entity = None
            repre_entity = self.get_representation_entity()
            if repre_entity:
                version_entity = ayon_api.get_version_by_id(
                    self._project_name, repre_entity["versionId"]
                )
            self._version_entity = version_entity
        return copy.deepcopy(self._version_entity)

    def get_workdir(self) -> Optional[str]:
        """Work directory of the selected task.

        Returns:
            Optional[str]: Path to work directory or None if task is not
                selected or the directory could not be calculated.

        """
        if self._workdir is _PLACEHOLDER:
            self._workdir = self._calculate_workdir()
        return self._workdir

    project_name = property(get_project_name)
    area = property(get_area)
    folder_id = property(get_folder_id)
    task_id = property(get_task_id)
    filepath = property(get_filepath)
    rootless_path = property(get_rootless_path)
    workfile_entity_id = property(get_workfile_entity_id)
    representation_id = property(get_representation_id)
    workfile_info = property(get_workfile_info)
    filename = property(get_filename)
    project_settings = property(get_project_settings)
    project_anatomy = property(get_project_anatomy)

    # --- Helper methods ---
    def is_workarea(self) -> bool:
        """Selection is related to workfiles in work area.

        Returns:
            bool: True if the area is work area.

        """
        return self._area == WorkfileAreaType.workarea

    def is_published(self) -> bool:
        """Selection is related to published workfiles.

        Returns:
            bool: True if the area is published workfiles.

        """
        return self._area == WorkfileAreaType.published

    def has_workfile(self) -> bool:
        """A workfile is selected.

        Returns:
            bool: True if a workfile is selected. False if the selection is
                related only to the area.

        """
        if self.is_published():
            return bool(self._representation_id)
        return bool(self._filepath)

    def _calculate_workdir(self) -> Optional[str]:
        # Avoid circular import
        from ayon_core.pipeline.workfile import get_workdir

        if not self._host_name:
            return None

        folder_entity = self.get_folder_entity()
        task_entity = self.get_task_entity()
        if not folder_entity or not task_entity:
            return None

        workdir = get_workdir(
            self.get_project_entity(),
            folder_entity,
            task_entity,
            self._host_name,
            anatomy=self.get_project_anatomy(),
            project_settings=self.get_project_settings(),
        )
        return str(workdir)


@dataclass
class WorkfileActionItem:
    """Item of workfile action.

    Action plugins return these items as possible actions to run for a given
        selection.

    Attributes:
        label (str): Text shown in UI.
        order (int): Order of the action in UI. Actions with lower order are
            shown first and have a higher chance to be visible as a quick
            action button.
        group_label (Optional[str]): Label of the group to which the action
            belongs. Grouped actions are shown in a submenu.
        icon (Union[IconBase, dict[str, Any], None]): Icon definition.
        tooltip (Optional[str]): Text shown on hover over the action.
        description (Optional[str]): Longer description of what the action
            does. Is shown under the tooltip.
        quick_action (bool): The action can be shown as a quick action
            button next to details of the selected workfile. Use 'False'
            for actions that should be available only in the context menu.
        data (Optional[DataType]): Action item data.
        identifier (Optional[str]): Identifier of the plugin which
            created the action item. Is filled automatically. Is not changed
            if is filled -> can lead to different plugin.

    """
    label: str
    order: int = 0
    group_label: Optional[str] = None
    icon: IconBase | dict[str, Any] | None = None
    tooltip: Optional[str] = None
    description: Optional[str] = None
    quick_action: bool = True
    data: Optional[DataType] = None
    # Is filled automatically
    identifier: str = None


@dataclass
class WorkfileActionRedirect:
    """Context to which should be the workfiles tool redirected.

    Attributes:
        folder_id (Optional[str]): Folder id to select.
        task_name (Optional[str]): Name of the task to select.
        workfile_name (Optional[str]): Filename of the workarea workfile to
            select.
        representation_id (Optional[str]): Id of published workfile
            representation to select.
        area (Optional[WorkfileAreaType]): Area to show. The area is not
            changed if is not filled.

    """
    folder_id: Optional[str] = None
    task_name: Optional[str] = None
    workfile_name: Optional[str] = None
    representation_id: Optional[str] = None
    area: Optional[WorkfileAreaType] = None

    def to_json_data(self) -> dict[str, Any]:
        area = self.area
        if area is not None:
            area = str(WorkfileAreaType(area))
        return {
            "folder_id": self.folder_id,
            "task_name": self.task_name,
            "workfile_name": self.workfile_name,
            "representation_id": self.representation_id,
            "area": area,
        }

    @classmethod
    def from_json_data(cls, data: dict[str, Any]) -> WorkfileActionRedirect:
        data = dict(data)
        area = data.get("area")
        if area is not None:
            data["area"] = WorkfileAreaType(area)
        return cls(**data)


@dataclass
class WorkfileActionOpenWorkfile:
    """Workfile that should be opened by the workfiles tool.

    The tool does open the workfile the same way as if a user would open
        it, so the user is asked what to do with unsaved changes and
        the tool is closed when the workfile is opened.

    Attributes:
        filepath (str): Path to the workfile to open.
        folder_id (Optional[str]): Folder id of the workfile context.
            Folder of the selection is used if is not filled.
        task_id (Optional[str]): Task id of the workfile context. Task of
            the selection is used if is not filled.

    """
    filepath: str
    folder_id: Optional[str] = None
    task_id: Optional[str] = None

    def to_json_data(self) -> dict[str, Any]:
        return {
            "filepath": self.filepath,
            "folder_id": self.folder_id,
            "task_id": self.task_id,
        }

    @classmethod
    def from_json_data(
        cls, data: dict[str, Any]
    ) -> WorkfileActionOpenWorkfile:
        return cls(**data)


@dataclass
class WorkfileActionResult:
    """Result of workfile action execution.

    Attributes:
        message (Optional[str]): Message to show in UI.
        success (bool): If the action was successful. Affects color of
            the message.
        form (Optional[ActionForm]): Form to show in UI.
        form_values (Optional[dict[str, Any]]): Values for the form. Can be
            used if the same form is re-shown e.g. because a user forgot to
            fill a required field.
        refresh (bool): The tool should refresh its content.
        redirect (Optional[WorkfileActionRedirect]): Context to which should
            be the tool redirected.
        open_workfile (Optional[WorkfileActionOpenWorkfile]): Workfile that
            should be opened by the tool. Refresh and redirect are applied
            only if the workfile was not opened, e.g. because a user
            cancelled it.
        duplicate_workfile (Optional[str]): Path to a workfile that should
            be duplicated by the tool. The tool does ask a user for
            the version and comment of the new workfile.
        close_tool (bool): The tool should be closed, e.g. because
            a workfile was opened by the action itself.

    """
    message: Optional[str] = None
    success: bool = True
    form: Optional[ActionForm] = None
    form_values: Optional[dict[str, Any]] = None
    refresh: bool = False
    redirect: Optional[WorkfileActionRedirect] = None
    open_workfile: Optional[WorkfileActionOpenWorkfile] = None
    duplicate_workfile: Optional[str] = None
    close_tool: bool = False

    def to_json_data(self) -> dict[str, Any]:
        form = self.form
        if form is not None:
            form = form.to_json_data()
        redirect = self.redirect
        if redirect is not None:
            redirect = redirect.to_json_data()
        open_workfile = self.open_workfile
        if open_workfile is not None:
            open_workfile = open_workfile.to_json_data()
        return {
            "message": self.message,
            "success": self.success,
            "form": form,
            "form_values": self.form_values,
            "refresh": self.refresh,
            "redirect": redirect,
            "open_workfile": open_workfile,
            "duplicate_workfile": self.duplicate_workfile,
            "close_tool": self.close_tool,
        }

    @classmethod
    def from_json_data(cls, data: dict[str, Any]) -> WorkfileActionResult:
        data = dict(data)
        form = data.get("form")
        if form is not None:
            data["form"] = ActionForm.from_json_data(form)
        redirect = data.get("redirect")
        if redirect is not None:
            data["redirect"] = WorkfileActionRedirect.from_json_data(redirect)
        open_workfile = data.get("open_workfile")
        if open_workfile is not None:
            data["open_workfile"] = (
                WorkfileActionOpenWorkfile.from_json_data(open_workfile)
            )
        return cls(**data)


@dataclass
class _ExecutionRequests:
    """Requests made by a plugin during execution of an action."""
    refresh: bool = False
    close_tool: bool = False
    redirect: Optional[WorkfileActionRedirect] = None
    open_workfile: Optional[WorkfileActionOpenWorkfile] = None
    duplicate_workfile: Optional[str] = None


class WorkfileActionPlugin(ABC):
    """Plugin for workfile actions.

    Plugin is responsible for getting action items and executing actions.

    Attributes:
        enabled (bool): Plugin is not used if is disabled.
        settings_category (Optional[str]): Settings category (addon name)
            where to look for settings of the plugin. Settings are expected
            under '<settings_category>/workfile_actions/<class name>'.

    """
    _log: Optional[logging.Logger] = None
    enabled: bool = True
    skip_discovery: bool = True
    settings_category: Optional[str] = None

    def __init__(self, context: WorkfileActionsContext) -> None:
        self._context = context
        self.apply_settings(context.get_project_settings())

    def apply_settings(self, project_settings: dict[str, Any]) -> None:
        """Apply project settings to the plugin.

        Default implementation does look for plugin settings in
            '<settings_category>/workfile_actions/<class name>' and set all
            values as attributes of the plugin.

        Args:
            project_settings (dict[str, Any]): Project settings. Studio
                settings if the context is not related to a project.

        """
        if not self.settings_category:
            return

        plugin_settings = (
            project_settings
            .get(self.settings_category, {})
            .get("workfile_actions", {})
            .get(self.__class__.__name__)
        )
        if not plugin_settings:
            return

        for key, value in plugin_settings.items():
            try:
                setattr(self, key, value)
            except AttributeError:
                self.log.debug(
                    f"Failed to set attribute '{key}' from settings."
                )

    @property
    def log(self) -> logging.Logger:
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def identifier(self) -> str:
        """Identifier of the plugin.

        Returns:
            str: Plugin identifier.

        """
        return self.__class__.__name__

    @property
    def host(self) -> Optional[AbstractHost]:
        """Current host integration."""
        return self._context.get_host()

    @property
    def host_name(self) -> Optional[str]:
        """Name of the current host."""
        return self._context.get_host_name()

    @abstractmethod
    def get_action_items(
        self, selection: WorkfileActionSelection
    ) -> list[WorkfileActionItem]:
        """Action items for the selection.

        Warning:
            The method can be called out of the main thread.

        Args:
            selection (WorkfileActionSelection): Selection.

        Returns:
            list[WorkfileActionItem]: Action items.

        """
        pass

    @abstractmethod
    def execute_action(
        self,
        selection: WorkfileActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        """Execute an action.

        Args:
            selection (WorkfileActionSelection): Selection wrapper. Can be
                used to get entities or get context of original selection.
            data (Optional[DataType]): Additional action item data.
            form_values (dict[str, Any]): Attribute values.

        Returns:
            Optional[WorkfileActionResult]: Result of the action execution.

        """
        pass

    # --- Helper methods to be used in 'execute_action' ---
    def redirect(
        self,
        *,
        folder_id: Optional[str] = None,
        task_name: Optional[str] = None,
        folder_entity: Optional[dict[str, Any]] = None,
        task_entity: Optional[dict[str, Any]] = None,
        workfile_name: Optional[str] = None,
        representation_id: Optional[str] = None,
        area: Optional[WorkfileAreaType] = None,
    ) -> None:
        """Request the tool to go to a different context.

        The context can be defined by entities or by folder id and task
            name. Passing task entity is enough to define both folder and
            task. Current context of the tool is used if the context is
            not defined, e.g. to only select a different workfile.

        The workfiles tool is refreshed before the redirect, so files
            created by the action can be selected.

        Example:
            >>> self.redirect(
            ...     task_entity=task_entity,
            ...     workfile_name="sh010_compositing_v003.nk",
            ... )

        Args:
            folder_id (Optional[str]): Folder id to select.
            task_name (Optional[str]): Name of task to select.
            folder_entity (Optional[dict[str, Any]]): Folder to select.
            task_entity (Optional[dict[str, Any]]): Task to select.
            workfile_name (Optional[str]): Filename of workarea workfile to
                select.
            representation_id (Optional[str]): Id of published workfile
                representation to select.
            area (Optional[WorkfileAreaType]): Area to show.

        """
        if task_entity is not None:
            folder_id = task_entity["folderId"]
            task_name = task_entity["name"]
        elif folder_entity is not None:
            folder_id = folder_entity["id"]

        if area is not None:
            area = WorkfileAreaType(area)

        self._context.request_redirect(WorkfileActionRedirect(
            folder_id=folder_id,
            task_name=task_name,
            workfile_name=workfile_name,
            representation_id=representation_id,
            area=area,
        ))

    def request_refresh(self) -> None:
        """Request the tool to refresh its content when action finishes."""
        self._context.request_refresh()

    def request_open_workfile(
        self,
        filepath: str,
        *,
        folder_id: Optional[str] = None,
        task_id: Optional[str] = None,
        folder_entity: Optional[dict[str, Any]] = None,
        task_entity: Optional[dict[str, Any]] = None,
    ) -> None:
        """Request the tool to open a workfile when action finishes.

        The workfile is opened the same way as if a user would open it in
            the tool, so the tool does ask what to do with unsaved changes
            and is closed when the workfile is opened. Context of
            the selection is used if the context is not defined.

        Requested refresh and redirect are applied only if the workfile
            was not opened, e.g. because a user cancelled it.

        Args:
            filepath (str): Path to the workfile to open.
            folder_id (Optional[str]): Folder id of the workfile context.
            task_id (Optional[str]): Task id of the workfile context.
            folder_entity (Optional[dict[str, Any]]): Folder of the workfile
                context.
            task_entity (Optional[dict[str, Any]]): Task of the workfile
                context.

        """
        if task_entity is not None:
            folder_id = task_entity["folderId"]
            task_id = task_entity["id"]
        elif folder_entity is not None:
            folder_id = folder_entity["id"]

        self._context.request_open_workfile(WorkfileActionOpenWorkfile(
            filepath=filepath,
            folder_id=folder_id,
            task_id=task_id,
        ))

    def request_duplicate_workfile(self, filepath: str) -> None:
        """Request the tool to duplicate a workfile when action finishes.

        The workfile is duplicated the same way as if a user would
            duplicate it in the tool, so the tool does ask for the version
            and comment of the new workfile.

        Args:
            filepath (str): Path to the workfile to duplicate.

        """
        self._context.request_duplicate_workfile(filepath)

    def request_close(self) -> None:
        """Request the tool to close when action finishes."""
        self._context.request_close()

    def ask_to_save_changes(
        self, form_values: dict[str, Any]
    ) -> Optional[WorkfileActionResult]:
        """Make sure a user decided what to do with unsaved changes.

        Helper for actions which do open a different workfile on their
            own. Use 'request_open_workfile' if the workfile can be opened
            by the tool, which takes care about unsaved changes too.

        Returns
            a result with a form if the current workfile has unsaved changes
            and a user did not decide what to do with them yet. The result
            should be returned from 'execute_action'. Current workfile is
            saved when the user asked for it by the form.

        Example:
            >>> def execute_action(self, selection, data, form_values):
            ...     result = self.ask_to_save_changes(form_values)
            ...     if result is not None:
            ...         return result
            ...     # Changes are handled, a workfile can be opened

        Args:
            form_values (dict[str, Any]): Form values passed to
                'execute_action'.

        Returns:
            Optional[WorkfileActionResult]: Result with form to show or None
                if the action can continue.

        """
        host = self.host
        if not isinstance(host, IWorkfileHost):
            return None

        if SAVE_CHANGES_FORM_KEY in form_values:
            if form_values[SAVE_CHANGES_FORM_KEY]:
                host.save_workfile(host.get_current_workfile())
            return None

        if not host.workfile_has_unsaved_changes():
            return None

        return WorkfileActionResult(
            form=ActionForm(
                title="Unsaved changes",
                fields=[
                    UILabelDef(
                        "There are unsaved changes to the current workfile.",
                        key="unsaved_changes_label",
                    ),
                    BoolDef(
                        SAVE_CHANGES_FORM_KEY,
                        default=True,
                        label="Save current workfile",
                    ),
                ],
                submit_label="Continue",
                cancel_label="Cancel",
            ),
        )


class WorkfileActionsContext:
    """Wrapper for workfile actions and their logic.

    Takes care about the public api of workfile actions and internal logic
        like discovery and initialization of plugins.

    Project of the host integration is used to get settings for plugins.
        Studio settings are used if host integration is not available.

    Args:
        project_settings (Optional[dict[str, Any]]): Prepared settings.
        addons_manager (Optional[AddonsManager]): Prepared addons manager.
        host (Optional[AbstractHost]): Host integration. Registered host is
            used if is not passed in.

    """
    def __init__(
        self,
        project_settings: Optional[dict[str, Any]] = None,
        addons_manager: Optional[AddonsManager] = None,
        host: Optional[AbstractHost] = _PLACEHOLDER,
    ) -> None:
        self._log = Logger.get_logger(self.__class__.__name__)

        self._addons_manager = addons_manager
        self._host = host
        self._lock = threading.RLock()

        # Attributes that are re-cached on reset
        self._project_settings = project_settings
        self._plugin_paths = None
        self._plugins = None

        self._execution_requests: Optional[_ExecutionRequests] = None

    def reset(
        self, project_settings: Optional[dict[str, Any]] = None
    ) -> None:
        """Reset context cache.

        Reset plugins and settings to reload them.

        Notes:
             Does not reset the cache of AddonsManger because there should not
                be a reason to do so.

        Args:
            project_settings (Optional[dict[str, Any]]): Prepared settings.

        """
        with self._lock:
            self._project_settings = project_settings
            self._plugin_paths = None
            self._plugins = None

    def get_addons_manager(self) -> AddonsManager:
        with self._lock:
            if self._addons_manager is None:
                self._addons_manager = AddonsManager(
                    settings=get_studio_settings()
                )
            return self._addons_manager

    def get_host(self) -> Optional[AbstractHost]:
        """Get current host integration.

        Returns:
            Optional[AbstractHost]: Host integration. Can be None if host
                integration is not registered -> probably not used in the
                host integration process.

        """
        if self._host is _PLACEHOLDER:
            from ayon_core.pipeline import registered_host

            self._host = registered_host()
        return self._host

    def get_host_name(self) -> Optional[str]:
        host = self.get_host()
        if host is None:
            return None
        return host.name

    def get_project_name(self) -> Optional[str]:
        """Project name of the host integration.

        Returns:
            Optional[str]: Project name or None if host integration is not
                available.

        """
        host = self.get_host()
        if host is None:
            return None
        return host.get_current_project_name()

    def get_project_settings(self) -> dict[str, Any]:
        """Settings used to set up the plugins.

        Returns:
            dict[str, Any]: Project settings or studio settings if project
                name is not available.

        """
        with self._lock:
            if self._project_settings is None:
                project_name = self.get_project_name()
                if project_name:
                    self._project_settings = get_project_settings(
                        project_name
                    )
                else:
                    self._project_settings = get_studio_settings()
            return copy.deepcopy(self._project_settings)

    def prepare_plugin_paths(self) -> None:
        """Prepare everything needed for the plugins discovery.

        Does prepare settings, addons and collect plugin paths. Does not
            import plugin files, so it is safe to call out of the main
            thread.

        """
        self._get_plugin_paths()

    def prepare_plugins(self) -> None:
        """Discover and initialize plugins if not done yet.

        Can be used to warm up the context before action items are needed.

        Warning:
            Should be called from the main thread, plugin discovery executes
                plugin files which may use host APIs.

        """
        self._get_plugins()

    def get_action_items(
        self, selection: WorkfileActionSelection
    ) -> list[WorkfileActionItem]:
        """Collect action items from all plugins for given selection.

        Args:
            selection (WorkfileActionSelection): Selection wrapper.

        Returns:
            list[WorkfileActionItem]: Action items sorted by order and
                label.

        """
        output = []
        for plugin_id, plugin in self._get_plugins().items():
            try:
                for action_item in plugin.get_action_items(selection):
                    if action_item.identifier is None:
                        action_item.identifier = plugin_id
                    output.append(action_item)

            except Exception:
                self._log.warning(
                    "Failed to get action items for"
                    f" plugin '{plugin.identifier}'",
                    exc_info=True,
                )
        output.sort(key=_action_items_sorter)
        return output

    def execute_action(
        self,
        identifier: str,
        selection: WorkfileActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> WorkfileActionResult:
        """Trigger action execution.

        Requests made by the plugin during the execution, like redirect or
            refresh, are added to the result.

        Args:
            identifier (str): Identifier of the plugin.
            selection (WorkfileActionSelection): Selection wrapper. Can be
                used to get what is selected in UI and to get access to
                entity cache.
            data (Optional[DataType]): Additional action item data.
            form_values (dict[str, Any]): Form values related to action.
                Usually filled if action returned response with form.

        Returns:
            WorkfileActionResult: Result of the action.

        """
        plugins_by_id = self._get_plugins()
        plugin = plugins_by_id[identifier]
        requests = _ExecutionRequests()
        self._execution_requests = requests
        try:
            result = plugin.execute_action(
                selection,
                data,
                form_values,
            )
        finally:
            self._execution_requests = None

        if result is None:
            result = WorkfileActionResult()

        if requests.refresh:
            result.refresh = True
        if requests.close_tool:
            result.close_tool = True
        if result.redirect is None:
            result.redirect = requests.redirect
        if result.open_workfile is None:
            result.open_workfile = requests.open_workfile
        if result.duplicate_workfile is None:
            result.duplicate_workfile = requests.duplicate_workfile
        return result

    def request_redirect(self, redirect: WorkfileActionRedirect) -> None:
        """Request redirect of the tool by currently executed action.

        Args:
            redirect (WorkfileActionRedirect): Where to redirect.

        """
        requests = self._get_execution_requests("redirect")
        if requests is not None:
            requests.redirect = redirect

    def request_open_workfile(
        self, open_workfile: WorkfileActionOpenWorkfile
    ) -> None:
        """Request the tool to open workfile by currently executed action.

        Args:
            open_workfile (WorkfileActionOpenWorkfile): Workfile to open.

        """
        requests = self._get_execution_requests("open workfile")
        if requests is not None:
            requests.open_workfile = open_workfile

    def request_duplicate_workfile(self, filepath: str) -> None:
        """Request the tool to duplicate workfile by executed action.

        Args:
            filepath (str): Path to the workfile to duplicate.

        """
        requests = self._get_execution_requests("duplicate workfile")
        if requests is not None:
            requests.duplicate_workfile = filepath

    def request_refresh(self) -> None:
        """Request refresh of the tool by currently executed action."""
        requests = self._get_execution_requests("refresh")
        if requests is not None:
            requests.refresh = True

    def request_close(self) -> None:
        """Request close of the tool by currently executed action."""
        requests = self._get_execution_requests("close")
        if requests is not None:
            requests.close_tool = True

    def _get_execution_requests(
        self, request_name: str
    ) -> Optional[_ExecutionRequests]:
        if self._execution_requests is None:
            self._log.warning(
                f"Requested '{request_name}' out of action execution."
                " The request is ignored."
            )
        return self._execution_requests

    def _get_plugin_paths(self) -> list[str]:
        with self._lock:
            if self._plugin_paths is not None:
                return self._plugin_paths

            # Make sure settings are cached
            self.get_project_settings()

            host_name = self.get_host_name()
            addons_manager = self.get_addons_manager()
            all_paths = [
                os.path.join(AYON_CORE_ROOT, "plugins", "workfile_actions")
            ]
            for addon in addons_manager.addons:
                if not isinstance(addon, IPluginPaths):
                    continue

                try:
                    paths = addon.get_workfile_action_plugin_paths(host_name)
                except Exception:
                    self._log.warning(
                        "Failed to get plugin paths for addon",
                        exc_info=True
                    )
                    continue

                if paths:
                    all_paths.extend(paths)

            self._plugin_paths = all_paths
            return self._plugin_paths

    def _get_plugins(self) -> dict[str, WorkfileActionPlugin]:
        with self._lock:
            if self._plugins is not None:
                return self._plugins

            result = discover_plugins(
                WorkfileActionPlugin, self._get_plugin_paths()
            )
            result.log_report()
            plugins = {}
            for cls in result.plugins:
                try:
                    plugin = cls(self)
                    if not plugin.enabled:
                        continue

                    plugin_id = plugin.identifier
                    if plugin_id not in plugins:
                        plugins[plugin_id] = plugin
                        continue

                    self._log.warning(
                        f"Duplicated plugins identifier found '{plugin_id}'."
                    )

                except Exception:
                    self._log.warning(
                        f"Failed to initialize plugin '{cls.__name__}'",
                        exc_info=True,
                    )
            self._plugins = plugins
            return self._plugins


def _action_items_sorter(item: WorkfileActionItem) -> tuple[int, str, str]:
    group_label = item.group_label
    label = item.label
    if group_label is None:
        group_label = label
        label = ""
    return item.order, group_label, label


class WorkfileSimpleActionPlugin(WorkfileActionPlugin):
    """Simple action plugin.

    This action will show exactly one action item defined by attributes
        on the class.

    Attributes:
        label: Label of the action item.
        order: Order of the action item.
        group_label: Label of the group to which the action belongs.
        icon: Icon definition shown next to label.
        tooltip: Text shown on hover over the action.
        description: Longer description of the action.
        quick_action: The action can be shown as a quick action button.
            Is available only in the context menu if is set to 'False'.

    """

    label: Optional[str] = None
    order: int = 0
    group_label: Optional[str] = None
    icon: IconBase | dict[str, Any] | None = None
    tooltip: Optional[str] = None
    description: Optional[str] = None
    quick_action: bool = True
    skip_discovery: bool = True

    @abstractmethod
    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        """Check if plugin is compatible with selection.

        Warning:
            The method can be called out of the main thread.

        Args:
            selection (WorkfileActionSelection): Selection information.

        Returns:
            bool: True if plugin is compatible with selection.

        """
        pass

    @abstractmethod
    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        """Process action based on selection.

        Args:
            selection (WorkfileActionSelection): Selection information.
            form_values (dict[str, Any]): Values from a form if there are any.

        Returns:
            Optional[WorkfileActionResult]: Result of the action.

        """
        pass

    def get_action_items(
        self, selection: WorkfileActionSelection
    ) -> list[WorkfileActionItem]:
        if self.is_compatible(selection):
            label = self.label or self.__class__.__name__
            return [
                WorkfileActionItem(
                    label=label,
                    order=self.order,
                    group_label=self.group_label,
                    icon=self.icon,
                    tooltip=self.tooltip,
                    description=self.description,
                    quick_action=self.quick_action,
                )
            ]
        return []

    def execute_action(
        self,
        selection: WorkfileActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        return self.execute_simple_action(selection, form_values)
