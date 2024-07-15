import os
import logging
import contextlib
from abc import ABC, abstractproperty

# NOTE can't import 'typing' because of issues in Maya 2020
#   - shiboken crashes on 'typing' module import


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

    @abstractproperty
    def name(self):
        """Host name."""

        pass

    def get_current_project_name(self):
        """
        Returns:
            Union[str, None]: Current project name.
        """

        return os.environ.get("AYON_PROJECT_NAME")

    def get_current_folder_path(self):
        """
        Returns:
            Union[str, None]: Current asset name.
        """

        return os.environ.get("AYON_FOLDER_PATH")

    def get_current_task_name(self):
        """
        Returns:
            Union[str, None]: Current task name.
        """

        return os.environ.get("AYON_TASK_NAME")

    def get_current_context(self):
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
