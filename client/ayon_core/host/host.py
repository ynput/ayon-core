from __future__ import annotations

import os
import logging
import contextlib
import typing
from typing import Optional, Any
from dataclasses import dataclass

import ayon_api

from ayon_core.lib import emit_event

from .constants import ContextChangeReason
from .abstract import AbstractHost

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy

    from .typing import HostContextData


@dataclass
class ContextChangeData:
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    task_entity: dict[str, Any]
    reason: ContextChangeReason
    anatomy: Anatomy


class HostBase(AbstractHost):
    """Base of host implementation class.

    Host is pipeline implementation of DCC application. This class should help
    to identify what must/should/can be implemented for specific functionality.

    Compared to 'avalon' concept:
    What was before considered as functions in host implementation folder. The
    host implementation should primarily care about adding ability of creation
    (mark products to be published) and optionally about referencing published
    representations as containers.

    Host may need extend some functionality like working with workfiles
    or loading. Not all host implementations may allow that for those purposes
    can be logic extended with implementing functions for the purpose. There
    are prepared interfaces to be able identify what must be implemented to
    be able use that functionality.
    - current statement is that it is not required to inherit from interfaces
        but all of the methods are validated (only their existence!)

    # Installation of host before (avalon concept):
    ```python
    from ayon_core.pipeline import install_host
    import ayon_core.hosts.maya.api as host

    install_host(host)
    ```

    # Installation of host now:
    ```python
    from ayon_core.pipeline import install_host
    from ayon_core.hosts.maya.api import MayaHost

    host = MayaHost()
    install_host(host)
    ```

    Todo:
        - move content of 'install_host' as method of this class
            - register host object
            - install global plugin paths
        - store registered plugin paths to this object
        - handle current context (project, asset, task)
            - this must be done in many separated steps
        - have it's object of host tools instead of using globals

    This implementation will probably change over time when more
        functionality and responsibility will be added.
    """

    _log = None

    def __init__(self):
        """Initialization of host.

        Register DCC callbacks, host specific plugin paths, targets etc.
        (Part of what 'install' did in 'avalon' concept.)

        Note:
            At this moment global "installation" must happen before host
            installation. Because of this current limitation it is recommended
            to implement 'install' method which is triggered after global
            'install'.
        """

        pass

    def install(self):
        """Install host specific functionality.

        This is where should be added menu with tools, registered callbacks
        and other host integration initialization.

        It is called automatically when 'ayon_core.pipeline.install_host' is
        triggered.
        """

        pass

    @property
    def log(self):
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    @property
    @abstractmethod
    def name(self) -> str:
        """Host name."""

        pass

    def get_current_project_name(self):
        """
        Returns:
            Union[str, None]: Current project name.
        """

        return os.environ.get("AYON_PROJECT_NAME")

    def get_current_folder_path(self) -> Optional[str]:
        """
        Returns:
            Union[str, None]: Current asset name.
        """

        return os.environ.get("AYON_FOLDER_PATH")

    def get_current_task_name(self) -> Optional[str]:
        """
        Returns:
            Union[str, None]: Current task name.
        """

        return os.environ.get("AYON_TASK_NAME")

    def get_current_context(self) -> "HostContextData":
        """Get current context information.

        This method should be used to get current context of host. Usage of
        this method can be crucial for host implementations in DCCs where
        can be opened multiple workfiles at one moment and change of context
        can't be caught properly.

        Returns:
            Dict[str, Union[str, None]]: Context with 3 keys 'project_name',
                'folder_path' and 'task_name'. All of them can be 'None'.
        """

        return {
            "project_name": self.get_current_project_name(),
            "folder_path": self.get_current_folder_path(),
            "task_name": self.get_current_task_name()
        }

    def set_current_context(
        self,
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        *,
        reason: ContextChangeReason = ContextChangeReason.undefined,
        project_entity: Optional[dict[str, Any]] = None,
        anatomy: Optional[Anatomy] = None,
    ) -> "HostContextData":
        """Set current context information.

        This method should be used to set current context of host. Usage of
        this method can be crucial for host implementations in DCCs where
        can be opened multiple workfiles at one moment and change of context
        can't be caught properly.

        Notes:
            This method should not care about change of workdir and expect any
                of the arguments.

        Args:
            folder_entity (Optional[dict[str, Any]]): Folder entity.
            task_entity (Optional[dict[str, Any]]): Task entity.
            reason (ContextChangeReason): Reason for context change.
            project_entity (Optional[dict[str, Any]]): Project entity data.
            anatomy (Optional[Anatomy]): Anatomy instance for the project.

        Returns:
            dict[str, Optional[str]]: Context information with project name,
                folder path and task name.

        """
        from ayon_core.pipeline import Anatomy

        folder_path = folder_entity["path"]
        task_name = task_entity["name"]

        context = self.get_current_context()
        # Don't do anything if context did not change
        if (
            context["folder_path"] == folder_path
            and context["task_name"] == task_name
        ):
            return context

        project_name = self.get_current_project_name()
        if project_entity is None:
            project_entity = ayon_api.get_project(project_name)

        if anatomy is None:
            anatomy = Anatomy(project_name, project_entity=project_entity)

        context_change_data = ContextChangeData(
            project_entity,
            folder_entity,
            task_entity,
            reason,
            anatomy,
        )
        self._before_context_change(context_change_data)
        self._set_current_context(context_change_data)
        self._after_context_change(context_change_data)

        return self._emit_context_change_event(
            project_name,
            folder_path,
            task_name,
        )

    def get_context_title(self):
        """Context title shown for UI purposes.

        Should return current context title if possible.

        Note:
            This method is used only for UI purposes so it is possible to
                return some logical title for contextless cases.
            Is not meant for "Context menu" label.

        Returns:
            str: Context title.
            None: Default title is used based on UI implementation.
        """

        # Use current context to fill the context title
        current_context = self.get_current_context()
        project_name = current_context["project_name"]
        folder_path = current_context["folder_path"]
        task_name = current_context["task_name"]
        items = []
        if project_name:
            items.append(project_name)
            if folder_path:
                items.append(folder_path.lstrip("/"))
                if task_name:
                    items.append(task_name)
        if items:
            return "/".join(items)
        return None

    @contextlib.contextmanager
    def maintained_selection(self):
        """Some functionlity will happen but selection should stay same.

        This is DCC specific. Some may not allow to implement this ability
        that is reason why default implementation is empty context manager.

        Yields:
            None: Yield when is ready to restore selected at the end.
        """

        try:
            yield
        finally:
            pass

    def _emit_context_change_event(
        self,
        project_name: str,
        folder_path: Optional[str],
        task_name: Optional[str],
    ) -> "HostContextData":
        """Emit context change event.

        Args:
            project_name (str): Name of the project.
            folder_path (Optional[str]): Path of the folder.
            task_name (Optional[str]): Name of the task.

        Returns:
            HostContextData: Data send to context change event.

        """
        data = {
            "project_name": project_name,
            "folder_path": folder_path,
            "task_name": task_name,
        }
        emit_event("taskChanged", data)
        return data

    def _set_current_context(
        self, context_change_data: ContextChangeData
    ) -> None:
        """Method that changes the context in host.

        Can be overriden for hosts that do need different handling of context
            than using environment variables.

        Args:
            context_change_data (ContextChangeData): Context change related
                data.

        """
        project_name = self.get_current_project_name()
        folder_path = None
        task_name = None
        if context_change_data.folder_entity:
            folder_path = context_change_data.folder_entity["path"]
            if context_change_data.task_entity:
                task_name = context_change_data.task_entity["name"]

        envs = {
            "AYON_PROJECT_NAME": project_name,
            "AYON_FOLDER_PATH": folder_path,
            "AYON_TASK_NAME": task_name,
        }

        # Update the Session and environments. Pop from environments all
        #   keys with value set to None.
        for key, value in envs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _before_context_change(self, context_change_data: ContextChangeData):
        """Before context is changed.

        This method is called before the context is changed in the host.

        Can be overridden to implement host specific logic.

        Args:
            context_change_data (ContextChangeData): Object with information
                about context change.

        """
        pass

    def _after_context_change(self, context_change_data: ContextChangeData):
        """After context is changed.

        This method is called after the context is changed in the host.

        Can be overridden to implement host specific logic.

        Args:
            context_change_data (ContextChangeData): Object with information
                about context change.

        """
        pass
