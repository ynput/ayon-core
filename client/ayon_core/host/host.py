from __future__ import annotations

import os
import logging
import contextlib
from abc import ABC, abstractmethod
import typing
from typing import Optional, Any

import ayon_api

from ayon_core.lib import emit_event

from .interfaces import IWorkfileHost

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class HostBase(ABC):
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

    def get_current_project_name(self) -> str:
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

    def get_current_context(self) -> dict[str, Optional[str]]:
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
        reason: Optional[str] = None,
        workdir: Optional[str] = None,
        project_entity: Optional[dict[str, Any]] = None,
        project_settings: Optional[dict[str, Any]] = None,
        anatomy: Optional["Anatomy"] = None,
    ):
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
            reason (Optional[str]): Reason for context change.
            workdir (Optional[str]): Work directory path.
            project_entity (Optional[dict[str, Any]]): Project entity data.
            project_settings (Optional[dict[str, Any]]): Project settings data.
            anatomy (Optional[Anatomy]): Anatomy instance for the project.

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

        self._before_context_change(
            project_entity,
            folder_entity,
            task_entity,
            anatomy,
            reason,
        )
        self._set_current_context(
            project_entity,
            folder_entity,
            task_entity,
            reason,
            workdir,
            anatomy,
            project_settings,
        )
        self._after_context_change(
            project_entity,
            folder_entity,
            task_entity,
            anatomy,
            reason,
        )

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
    ):
        """Emit context change event.

        Args:
            project_name (str): Name of the project.
            folder_path (Optional[str]): Path of the folder.
            task_name (Optional[str]): Name of the task.

        """
        data = {
            "project_name": project_name,
            "folder_path": folder_path,
            "task_name": task_name,
        }
        emit_event("taskChanged", data)
        return data

    def _set_current_context(
        self,
        project_entity: dict[str, Any],
        folder_entity: Optional[dict[str, Any]],
        task_entity: Optional[dict[str, Any]],
        reason: Optional[str],
        workdir: Optional[str],
        anatomy: Optional["Anatomy"],
        project_settings: Optional[dict[str, Any]],
    ):
        from ayon_core.pipeline.workfile import get_workdir

        project_name = self.get_current_project_name()
        folder_path = None
        task_name = None
        if folder_entity:
            folder_path = folder_entity["path"]
            if task_entity:
                task_name = task_entity["name"]

        if (
            workdir is None
            and isinstance(self, IWorkfileHost)
            and folder_entity
        ):
            if project_entity is None:
                project_entity = ayon_api.get_project(project_name)

            workdir = get_workdir(
                project_entity,
                folder_entity,
                task_entity,
                self.name,
                anatomy=anatomy,
                project_settings=project_settings,
            )

        envs = {
            "AYON_PROJECT_NAME": project_name,
            "AYON_FOLDER_PATH": folder_path,
            "AYON_TASK_NAME": task_name,
            "AYON_WORKDIR": workdir,
        }

        # Update the Session and environments. Pop from environments all
        #   keys with value set to None.
        for key, value in envs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _before_context_change(
        self,
        project_entity: dict[str, Any],
        folder_entity: Optional[dict[str, Any]],
        task_entity: Optional[dict[str, Any]],
        anatomy: "Anatomy",
        reason: Optional[str],
    ):
        """Before context is changed.

        This method is called before the context is changed in the host.

        Can be overriden to implement host specific logic.

        Args:
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            reason (Optional[str]): Reason for context change.

        """
        pass

    def _after_context_change(
        self,
        project_entity: dict[str, Any],
        folder_entity: dict[str, Any],
        task_entity: dict[str, Any],
        anatomy: "Anatomy",
        reason: Optional[str],
    ):
        """After context is changed.

        This method is called after the context is changed in the host.

        Can be overriden to implement host specific logic.

        Args:
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            reason (Optional[str]): Reason for context change.

        """
        pass
