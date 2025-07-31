"""Addon interfaces for AYON."""
from __future__ import annotations

import warnings
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable, Optional, Type

from ayon_core import resources

if TYPE_CHECKING:
    from qtpy import QtWidgets

    from ayon_core.addon.base import AddonsManager
    from ayon_core.pipeline.traits import TraitBase
    from ayon_core.tools.tray.ui.tray import TrayManager


class _AYONInterfaceMeta(ABCMeta):
    """AYONInterface metaclass to print proper string."""

    def __str__(cls):
        return f"<'AYONInterface.{cls.__name__}'>"

    def __repr__(cls):
        return str(cls)


class AYONInterface(metaclass=_AYONInterfaceMeta):
    """Base class of Interface that can be used as Mixin with abstract parts.

    This is way how AYON addon can define that contains specific predefined
    functionality.

    Child classes of AYONInterface may be used as mixin in different
    AYON addons which means they have to have implemented methods defined
    in the interface. By default, interface does not have any abstract parts.
    """

    log = None


class IPluginPaths(AYONInterface):
    """Addon wants to register plugin paths."""

    def get_plugin_paths(self) -> dict[str, list[str]]:
        """Return plugin paths for addon.

        This method was abstract (required) in the past, so raise the required
            'core' addon version when 'get_plugin_paths' is removed from
            addon.

        Deprecated:
            Please implement specific methods 'get_create_plugin_paths',
                'get_load_plugin_paths', 'get_inventory_action_paths' and
                'get_publish_plugin_paths' to return plugin paths.

        Returns:
            dict[str, list[str]]: Plugin paths for addon.

        """
        return {}

    def _get_plugin_paths_by_type(
            self, plugin_type: str) -> list[str]:
        """Get plugin paths by type.

        Args:
            plugin_type (str): Type of plugin paths to get.

        Returns:
            list[str]: List of plugin paths.

        """
        paths = self.get_plugin_paths()
        if not paths or plugin_type not in paths:
            return []

        paths = paths[plugin_type]
        if not paths:
            return []

        if not isinstance(paths, (list, tuple, set)):
            paths = [paths]

        new_function_name = "get_launcher_action_paths"
        if plugin_type == "create":
            new_function_name = "get_create_plugin_paths"
        elif plugin_type == "load":
            new_function_name = "get_load_plugin_paths"
        elif plugin_type == "publish":
            new_function_name = "get_publish_plugin_paths"
        elif plugin_type == "inventory":
            new_function_name = "get_inventory_action_paths"

        warnings.warn(
            f"Addon '{self.name}' returns '{plugin_type}' paths using"
            " 'get_plugin_paths' method. Please implement"
            f" '{new_function_name}' instead.",
            DeprecationWarning,
            stacklevel=2

        )
        return paths

    def get_launcher_action_paths(self) -> list[str]:
        """Receive launcher actions paths.

        Give addons ability to add launcher actions paths.

        Returns:
            list[str]: List of launcher action paths.

        """
        return self._get_plugin_paths_by_type("actions")

    def get_create_plugin_paths(self, host_name: str) -> list[str]:
        """Receive create plugin paths.

        Give addons ability to add create plugin paths based on host name.

        Notes:
            Default implementation uses 'get_plugin_paths' and always return
                all create plugin paths.

        Args:
            host_name (str): For which host are the plugins meant.

        Returns:
            list[str]: List of create plugin paths.

        """
        return self._get_plugin_paths_by_type("create")

    def get_load_plugin_paths(self, host_name: str) -> list[str]:
        """Receive load plugin paths.

        Give addons ability to add load plugin paths based on host name.

        Notes:
            Default implementation uses 'get_plugin_paths' and always return
                all load plugin paths.

        Args:
            host_name (str): For which host are the plugins meant.

        Returns:
            list[str]: List of load plugin paths.

        """
        return self._get_plugin_paths_by_type("load")

    def get_publish_plugin_paths(self, host_name: str) -> list[str]:
        """Receive publish plugin paths.

        Give addons ability to add publish plugin paths based on host name.

        Notes:
           Default implementation uses 'get_plugin_paths' and always return
               all publish plugin paths.

        Args:
           host_name (str): For which host are the plugins meant.

        Returns:
            list[str]: List of publish plugin paths.

        """
        return self._get_plugin_paths_by_type("publish")

    def get_inventory_action_paths(self, host_name: str) -> list[str]:
        """Receive inventory action paths.

        Give addons ability to add inventory action plugin paths.

        Notes:
           Default implementation uses 'get_plugin_paths' and always return
               all publish plugin paths.

        Args:
           host_name (str): For which host are the plugins meant.

        Returns:
            list[str]: List of inventory action plugin paths.

        """
        return self._get_plugin_paths_by_type("inventory")


class ITrayAddon(AYONInterface):
    """Addon has special procedures when used in Tray tool.

    Important:
        The addon. still must be usable if is not used in tray even if it
        would do nothing.

    """
    manager: AddonsManager
    tray_initialized = False
    _tray_manager: TrayManager = None
    _admin_submenu = None

    @abstractmethod
    def tray_init(self) -> None:
        """Initialization part of tray implementation.

        Triggered between `initialization` and `connect_with_addons`.

        This is where GUIs should be loaded or tray specific parts should be
        prepared

        """

    @abstractmethod
    def tray_menu(self, tray_menu: QtWidgets.QMenu) -> None:
        """Add addon's action to tray menu."""

    @abstractmethod
    def tray_start(self) -> None:
        """Start procedure in tray tool."""

    @abstractmethod
    def tray_exit(self) -> None:
        """Cleanup method which is executed on tray shutdown.

        This is place where all threads should be shut.

        """

    def execute_in_main_thread(self, callback: Callable) -> None:
        """Pushes callback to the queue or process 'callback' on a main thread.

        Some callbacks need to be processed on main thread (menu actions
        must be added on main thread else they won't get triggered etc.)

        Args:
            callback (Callable): Function to be executed on main thread

        """
        if not self.tray_initialized:
            # TODO (Illicit): Called without initialized tray, still
            #   main thread needed.
            try:
                callback()

            except Exception:  # noqa: BLE001
                self.log.warning(
                    "Failed to execute %s callback in main thread",
                    str(callback), exc_info=True)

            return
        self._tray_manager.tray_manager.execute_in_main_thread(callback)

    def show_tray_message(
            self,
            title: str,
            message: str,
            icon: Optional[QtWidgets.QSystemTrayIcon] = None,
            msecs: Optional[int] = None) -> None:
        """Show tray message.

        Args:
            title (str): Title of message.
            message (str): Content of message.
            icon (QSystemTrayIcon.MessageIcon): Message's icon. Default is
                Information icon, may differ by Qt version.
            msecs (int): Duration of message visibility in milliseconds.
                Default is 10000 msecs, may differ by Qt version.
        """
        if self._tray_manager:
            self._tray_manager.show_tray_message(title, message, icon, msecs)

    def add_doubleclick_callback(self, callback: Callable) -> None:
        """Add callback to be triggered on tray icon double click."""
        if hasattr(self.manager, "add_doubleclick_callback"):
            self.manager.add_doubleclick_callback(self, callback)

    @staticmethod
    def admin_submenu(tray_menu: QtWidgets.QMenu) -> QtWidgets.QMenu:
        """Get or create admin submenu.

        Returns:
            QtWidgets.QMenu: Admin submenu.

        """
        if ITrayAddon._admin_submenu is None:
            from qtpy import QtWidgets

            admin_submenu = QtWidgets.QMenu("Admin", tray_menu)
            admin_submenu.menuAction().setVisible(False)
            ITrayAddon._admin_submenu = admin_submenu
        return ITrayAddon._admin_submenu

    @staticmethod
    def add_action_to_admin_submenu(
            label: str, tray_menu: QtWidgets.QMenu) -> QtWidgets.QAction:
        """Add action to admin submenu.

        Args:
            label (str): Label of action.
            tray_menu (QtWidgets.QMenu): Tray menu to add action to.

        Returns:
            QtWidgets.QAction: Action added to admin submenu

        """
        from qtpy import QtWidgets

        menu = ITrayAddon.admin_submenu(tray_menu)
        action = QtWidgets.QAction(label, menu)
        menu.addAction(action)
        if not menu.menuAction().isVisible():
            menu.menuAction().setVisible(True)
        return action


class ITrayAction(ITrayAddon):
    """Implementation of Tray action.

    Add action to tray menu which will trigger `on_action_trigger`.
    It is expected to be used for showing tools.

    Methods `tray_start`, `tray_exit` and `connect_with_addons` are overridden
    as it's not expected that action will use them. But it is possible if
    necessary.
    """

    admin_action = False
    _action_item = None

    @property
    @abstractmethod
    def label(self) -> str:
        """Service label showed in menu."""

    @abstractmethod
    def on_action_trigger(self) -> None:
        """What happens on actions click."""

    def tray_menu(self, tray_menu: QtWidgets.QMenu) -> None:
        """Add action to tray menu."""
        from qtpy import QtWidgets

        if self.admin_action:
            action = self.add_action_to_admin_submenu(self.label, tray_menu)
        else:
            action = QtWidgets.QAction(self.label, tray_menu)
            tray_menu.addAction(action)

        action.triggered.connect(self.on_action_trigger)
        self._action_item = action

    def tray_start(self) -> None:  # noqa: PLR6301
        """Start procedure in tray tool."""
        return

    def tray_exit(self) -> None:  # noqa: PLR6301
        """Cleanup method which is executed on tray shutdown."""
        return


class ITrayService(ITrayAddon):
    """Tray service Interface."""
    # Module's property
    menu_action: QtWidgets.QAction = None

    # Class properties
    _services_submenu: QtWidgets.QMenu = None
    _icon_failed: QtWidgets.QIcon = None
    _icon_running: QtWidgets.QIcon = None
    _icon_idle: QtWidgets.QIcon = None

    @property
    @abstractmethod
    def label(self) -> str:
        """Service label showed in menu."""

    # TODO (Illicit): be able to get any sort of information to show/print
    # @abstractmethod
    # def get_service_info(self):
    #     pass

    @staticmethod
    def services_submenu(tray_menu: QtWidgets.QMenu) -> QtWidgets.QMenu:
        """Get or create services submenu.

        Returns:
            QtWidgets.QMenu: Services submenu.

        """
        if ITrayService._services_submenu is None:
            from qtpy import QtWidgets

            services_submenu = QtWidgets.QMenu("Services", tray_menu)
            services_submenu.menuAction().setVisible(False)
            ITrayService._services_submenu = services_submenu
        return ITrayService._services_submenu

    @staticmethod
    def add_service_action(action: QtWidgets.QAction) -> None:
        """Add service action to services submenu."""
        ITrayService._services_submenu.addAction(action)
        if not ITrayService._services_submenu.menuAction().isVisible():
            ITrayService._services_submenu.menuAction().setVisible(True)

    @staticmethod
    def _load_service_icons() -> None:
        """Load service icons."""
        from qtpy import QtGui

        ITrayService._failed_icon = QtGui.QIcon(
            resources.get_resource("icons", "circle_red.png")
        )
        ITrayService._icon_running = QtGui.QIcon(
            resources.get_resource("icons", "circle_green.png")
        )
        ITrayService._icon_idle = QtGui.QIcon(
            resources.get_resource("icons", "circle_orange.png")
        )

    @staticmethod
    def get_icon_running() -> QtWidgets.QIcon:
        """Get running icon.

        Returns:
            QtWidgets.QIcon: Returns "running" icon.

        """
        if ITrayService._icon_running is None:
            ITrayService._load_service_icons()
        return ITrayService._icon_running

    @staticmethod
    def get_icon_idle() -> QtWidgets.QIcon:
        """Get idle icon.

        Returns:
            QtWidgets.QIcon: Returns "idle" icon.

        """
        if ITrayService._icon_idle is None:
            ITrayService._load_service_icons()
        return ITrayService._icon_idle

    @staticmethod
    def get_icon_failed() -> QtWidgets.QIcon:
        """Get failed icon.

        Returns:
            QtWidgets.QIcon: Returns "failed" icon.

        """
        if ITrayService._icon_failed is None:
            ITrayService._load_service_icons()
        return ITrayService._icon_failed

    def tray_menu(self, tray_menu: QtWidgets.QMenu) -> None:
        """Add service to tray menu."""
        from qtpy import QtWidgets

        action = QtWidgets.QAction(
            self.label,
            self.services_submenu(tray_menu)
        )
        self.menu_action = action

        self.add_service_action(action)

        self.set_service_running_icon()

    def set_service_running_icon(self) -> None:
        """Change icon of an QAction to green circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_running())

    def set_service_failed_icon(self) -> None:
        """Change icon of an QAction to red circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_failed())

    def set_service_idle_icon(self) -> None:
        """Change icon of an QAction to orange circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_idle())


class IHostAddon(AYONInterface):
    """Addon which also contain a host implementation."""

    @property
    @abstractmethod
    def host_name(self) -> str:
        """Name of host which addon represents."""

    def get_workfile_extensions(self) -> list[str]:  # noqa: PLR6301
        """Define workfile extensions for host.

        Not all hosts support workfiles thus this is optional implementation.

        Returns:
            List[str]: Extensions used for workfiles with dot.

        """
        return []


class ITraits(AYONInterface):
    """Interface for traits."""

    @abstractmethod
    def get_addon_traits(self) -> list[Type[TraitBase]]:
        """Get trait classes for the addon.

        Returns:
            list[Type[TraitBase]]: Traits for the addon.

        """
