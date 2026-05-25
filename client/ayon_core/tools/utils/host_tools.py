"""Single access point to all tools usable in hosts.

It is possible to create `HostToolsHelper` in host implementation or
use singleton approach with global functions (using helper anyway).
"""
from __future__ import annotations

import os

import pyblish.api
from typing import TYPE_CHECKING, Optional, Literal

from ayon_core.host import ILoadHost, IPublishHost
from ayon_core.lib import Logger
from ayon_core.pipeline import registered_host

from .lib import qt_app_context

if TYPE_CHECKING:
    from qtpy.QtWidgets import QWidget
    from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend

TPublisherTabs = Literal["create", "publish", "report", "details"]
TToolNames = Literal[
    "workfiles",
    "loader",
    "libraryloader",
    "sceneinventory",
    "publisher",
    "experimental_tools",
    "publish"
]


class HostToolsHelper:
    """Create and cache tool windows in memory.

    Almost all methods expect parent widget but the parent is used only on
    first tool creation.

    Class may also contain tools that are available only for one or few hosts.
    """

    def __init__(self, parent=None):
        self._log = None
        # Global parent for all tools (may and may not be set)
        self._parent = parent

        # Prepare attributes for all tools
        self._workfiles_tool = None
        self._loader_tool = None
        self._publisher_tool = None
        self._scene_inventory_tool = None
        self._experimental_tools_dialog = None

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    def get_workfiles_tool(self, parent):
        """Create, cache and return workfiles tool window."""
        if self._workfiles_tool is None:
            from ayon_core.tools.workfiles.widgets import WorkfilesToolWindow

            workfiles_window = WorkfilesToolWindow(parent=parent)
            self._workfiles_tool = workfiles_window

        return self._workfiles_tool

    def show_workfiles(
            self,
            parent=None,
            *,
            use_context: Optional[bool] = False,
            save: Optional[bool] = None,
            on_top: Optional[bool] = None
    ) -> Optional[QWidget]:
        """Workfiles tool for changing context and saving workfiles."""

        with qt_app_context():
            workfiles_tool = self.get_workfiles_tool(parent)
            workfiles_tool.ensure_visible(use_context, save, on_top)

        return workfiles_tool

    def get_loader_tool(self, parent):
        """Create, cache and return loader tool window."""
        if self._loader_tool is None:
            from ayon_core.tools.loader.ui import LoaderWindow
            from ayon_core.tools.loader import LoaderController

            host = registered_host()
            ILoadHost.validate_load_methods(host)

            controller = LoaderController(host=host)
            loader_window = LoaderWindow(
                controller=controller,
                parent=parent or self._parent
            )

            self._loader_tool = loader_window

        return self._loader_tool

    def show_loader(
            self,
            parent: Optional[QWidget] = None) -> QWidget:
        """Loader tool for loading representations.

        Args:
            parent (QWidget): parent widget

        Returns:
            QWidget of the tool shown.

        """
        with qt_app_context():
            loader_tool = self.get_loader_tool(parent)

            loader_tool.show()
            loader_tool.raise_()
            loader_tool.activateWindow()
            loader_tool.showNormal()
            loader_tool.refresh()
        return loader_tool

    def get_scene_inventory_tool(self, parent):
        """Create, cache and return scene inventory tool window."""
        if self._scene_inventory_tool is None:
            host = registered_host()
            ILoadHost.validate_load_methods(host)

            from ayon_core.tools.sceneinventory.window import (
                SceneInventoryWindow)

            scene_inventory_window = SceneInventoryWindow(
                parent=parent or self._parent
            )
            self._scene_inventory_tool = scene_inventory_window

        return self._scene_inventory_tool

    def show_scene_inventory(
            self, parent: Optional[QWidget] = None) -> QWidget:
        """Show tool maintain loaded containers."""
        with qt_app_context():
            scene_inventory_tool = self.get_scene_inventory_tool(parent)
            scene_inventory_tool.show()
            scene_inventory_tool.refresh()

            # Pull window to the front.
            scene_inventory_tool.raise_()
            scene_inventory_tool.activateWindow()
            scene_inventory_tool.showNormal()

        return scene_inventory_tool

    def get_library_loader_tool(self, parent):
        """Create, cache and return library loader tool window."""
        return self.get_loader_tool(parent)

    def show_library_loader(self, parent: Optional[QWidget] = None) -> QWidget:
        """Loader tool for loading representations from library project.

        Args:
            parent (QWidget): parent widget

        Returns:
            QWidget of the tool shown.

        """
        return self.show_loader(parent)

    def show_publish(
            self, parent: Optional[QWidget] = None) -> QWidget:
        """Try showing the most desirable publish GUI

        This function cycles through the currently registered
        graphical user interfaces, if any, and presents it to
        the user.
        """

        pyblish_show = self._discover_pyblish_gui()
        return pyblish_show(parent)

    def _discover_pyblish_gui(self):
        """Return the most desirable of the currently registered GUIs"""
        # Prefer last registered
        guis = list(reversed(pyblish.api.registered_guis()))
        for gui in guis:
            try:
                gui = __import__(gui).show
            except (ImportError, AttributeError):
                continue
            else:
                return gui

        raise ImportError("No Pyblish GUI found")

    def get_experimental_tools_dialog(self, parent=None):
        """Dialog of experimental tools.

        For some hosts it is not easy to modify menu of tools. For
        those cases was added experimental tools dialog which is Qt based
        and can dynamically filled by experimental tools so
        host need only single "Experimental tools" button to see them.

        Dialog can be also empty with a message that there are not available
        experimental tools.
        """
        if self._experimental_tools_dialog is None:
            from ayon_core.tools.experimental_tools import (
                ExperimentalToolsDialog
            )

            self._experimental_tools_dialog = ExperimentalToolsDialog(parent)
        return self._experimental_tools_dialog

    def show_experimental_tools_dialog(
            self, parent: Optional[QWidget] = None) -> QWidget:
        """Show dialog with experimental tools.

        Args:
            parent (QWidget): parent widget.

        Returns:
            QWidget of the tool shown.

        """
        with qt_app_context():
            dialog = self.get_experimental_tools_dialog(parent)

            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            dialog.showNormal()

        return dialog

    def get_publisher_tool(self, parent=None, controller=None):
        """Create, cache and return publisher window."""

        if self._publisher_tool is None:
            from ayon_core.tools.publisher.window import PublisherWindow

            host = registered_host()
            IPublishHost.validate_publish_methods(host)

            publisher_window = PublisherWindow(
                controller=controller,
                parent=parent or self._parent
            )
            self._publisher_tool = publisher_window

        return self._publisher_tool

    def show_publisher_tool(
            self,
            parent: Optional[QWidget] = None,
            controller: Optional[AbstractPublisherFrontend] = None,
            tab: Optional[TPublisherTabs] = None) -> QWidget:
        with qt_app_context():
            window = self.get_publisher_tool(parent, controller)
            if tab:
                window.set_current_tab(tab)
            window.make_sure_is_visible()
            return window

    def get_tool_by_name(
            self,
            tool_name: TToolNames,
            parent: Optional[QWidget] = None,
            *args,
            **kwargs
    ) -> Optional[QWidget]:
        """Show tool by its name.

        This is helper for
        """
        if tool_name == "workfiles":
            return self.get_workfiles_tool(parent)

        if tool_name == "loader":
            return self.get_loader_tool(parent)

        if tool_name == "libraryloader":
            return self.get_library_loader_tool(parent)

        if tool_name == "sceneinventory":
            return self.get_scene_inventory_tool(parent)

        if tool_name == "publisher":
            return self.get_publisher_tool(parent, *args, **kwargs)

        if tool_name == "experimental_tools":
            return self.get_experimental_tools_dialog(parent)

        if tool_name == "publish":
            self.log.info("Can't return publish tool window.")
            return None

        self.log.warning(
            'Cannot show unknown tool name: "%s"', tool_name)
        return None

    def show_tool_by_name(
            self,
            tool_name: TToolNames,
            parent: Optional[QWidget] = None,
            *args,
            **kwargs
    ) -> Optional[QWidget]:
        """Show tool by its name.

        This is helper for
        """
        tool = None
        if tool_name == "workfiles":
            tool = self.show_workfiles(parent, *args, **kwargs)

        elif tool_name == "loader":
            tool = self.show_loader(parent)

        elif tool_name == "libraryloader":
            tool = self.show_library_loader(parent)

        elif tool_name == "sceneinventory":
            tool = self.show_scene_inventory(parent)

        elif tool_name == "publish":
            tool = self.show_publish(parent)

        elif tool_name == "publisher":
            tool = self.show_publisher_tool(parent, *args, **kwargs)

        elif tool_name == "experimental_tools":
            tool = self.show_experimental_tools_dialog(parent)

        else:
            self.log.warning(
                "Can't show unknown tool name: \"%s\"", tool_name)
            return None
        return tool


class _SingletonPoint:
    """Singleton access to host tools.

    Some hosts don't have ability to create 'HostToolsHelper' object anc can
    only register function callbacks. For those cases is created this singleton
    point where 'HostToolsHelper' is created "in shared memory".
    """
    helper = None

    @classmethod
    def _create_helper(cls):
        if cls.helper is None:
            cls.helper = HostToolsHelper()

    @classmethod
    def show_tool_by_name(
            cls,
            tool_name: TToolNames,
            parent: Optional[QWidget] = None,
            *args,
            **kwargs) -> Optional[QWidget]:
        cls._create_helper()
        return cls.helper.show_tool_by_name(tool_name, parent, *args, **kwargs)

    @classmethod
    def get_tool_by_name(cls, tool_name, parent=None, *args, **kwargs):
        cls._create_helper()
        return cls.helper.get_tool_by_name(tool_name, parent, *args, **kwargs)


# Function callbacks using singleton access point
def get_tool_by_name(tool_name, parent=None, *args, **kwargs):
    return _SingletonPoint.get_tool_by_name(tool_name, parent, *args, **kwargs)


def show_tool_by_name(
        tool_name: TToolNames,
        parent: Optional[QWidget] = None,
        *args,
        **kwargs) -> Optional[QWidget]:
    """Show tool by its name.

    Args:
        tool_name: tool name,
        parent: tool parent,
        *args: tool args,
        **kwargs: tool kwargs,

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name(
        tool_name, parent, *args, **kwargs)


def show_workfiles(*args, **kwargs) -> Optional[QWidget]:
    """Show workfiles tool.

    Args:
        *args: tool args,
        **kwargs: tool kwargs,

    Returns:
        QWidget of the tool
    """
    return _SingletonPoint.show_tool_by_name(
        "workfiles", *args, **kwargs
    )


def show_loader(
        parent: Optional[QWidget] = None,
        *,
        use_context: bool = False) -> Optional[QWidget]:
    """Show loader tool.

    Args:
        parent: tool parent,
        use_context: use context,

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name(
        "loader", parent, use_context=use_context
    )


def show_library_loader(
        parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Show library loader tool.

    Args:
        parent: tool parent,

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name("libraryloader", parent)


def show_scene_inventory(
        parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Show scene inventory tool.

    Args:
        parent: tool parent,

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name(
        "sceneinventory", parent)


def show_publish(parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Show publish tool.

    Args:
        parent: tool parent

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name("publish", parent)


def show_publisher(
        parent: Optional[QWidget] = None,
        **kwargs) -> Optional[QWidget]:
    """Show publisher tool.

    Args:
        parent: tool parent,
        **kwargs: tool kwargs,

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name(
        "publisher", parent, **kwargs)


def show_experimental_tools_dialog(
        parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Show experimental tools dialog.

    Args:
        parent: tool parent

    Returns:
        QWidget of the tool

    """
    return _SingletonPoint.show_tool_by_name(
        "experimental_tools", parent)


def get_pyblish_icon():
    pyblish_dir = os.path.abspath(os.path.dirname(pyblish.api.__file__))
    icon_path = os.path.join(pyblish_dir, "icons", "logo-32x32.svg")
    if os.path.exists(icon_path):
        return icon_path
    return None
