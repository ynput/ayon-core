# -*- coding: utf-8 -*-
"""Base class for AYON addons."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import sys
import time
import inspect
import logging
import threading
import warnings
from uuid import uuid4
from urllib.parse import urlencode
from types import ModuleType
import typing
from typing import Any

import ayon_api

from ayon_core import AYON_CORE_ROOT, __version__
from ayon_core.lib import (
    Logger,
    is_dev_mode_enabled,
    get_launcher_storage_dir,
    is_headless_mode_enabled,
)
from ayon_core.settings import get_studio_settings

from .interfaces import (
    IPluginPaths,
    IHostAddon,
)

if typing.TYPE_CHECKING:
    import click

    from ayon_core.host import HostBase

# Files that will be always ignored on addons import
IGNORED_FILENAMES = {
    "__pycache__",
}
# Files ignored on addons import from "./ayon_core/modules"
IGNORED_DEFAULT_FILENAMES = {
    "__init__.py",
}


class ProcessPreparationError(Exception):
    """Exception that can be used when process preparation failed.

    The message is shown to user (either as UI dialog or printed). If
        different error is raised a "generic" error message is shown to user
        with option to copy error message to clipboard.

    """
    pass


class ProcessContext:
    """Hold context of process that is going to be started.

    Right now the context is simple, having information about addon that wants
        to trigger preparation and possibly project name for which it should
        happen.

    Preparation for process can be required for ayon-core or any other addon.
        It can be, change of environment variables, or request login to
        a project management.

    At the moment of creation is 'ProcessContext' only data holder, but that
        might change in future if there will be need.

    Args:
        addon_name (str): Addon name which triggered process.
        addon_version (str): Addon version which triggered process.
        project_name (str | None): Project name. Can be filled in case
            process is triggered for specific project. Some addons can have
            different behavior based on project. Value is NOT autofilled.
        headless (bool | None): Is process running in headless mode. Value
            is filled with value based on state set in AYON launcher.

    """
    def __init__(
        self,
        addon_name: str,
        addon_version: str,
        project_name: str | None = None,
        headless: bool | None = None,
        **kwargs,
    ):
        if headless is None:
            headless = is_headless_mode_enabled()
        self.addon_name: str = addon_name
        self.addon_version: str = addon_version
        self.project_name: str | None = project_name
        self.headless: bool = headless

        if kwargs:
            unknown_keys = ", ".join([f'"{key}"' for key in kwargs.keys()])
            print(f"Unknown keys in ProcessContext: {unknown_keys}")


def _get_ayon_bundle_data() -> tuple[
    dict[str, Any], dict[str, Any] | None
]:
    studio_bundle_name = os.environ.get("AYON_STUDIO_BUNDLE_NAME")
    project_bundle_name = os.getenv("AYON_BUNDLE_NAME")
    # If AYON launcher <1.4.0 was used
    if not studio_bundle_name:
        studio_bundle_name = project_bundle_name
    bundles = ayon_api.get_bundles()["bundles"]
    studio_bundle = next(
        (
            bundle
            for bundle in bundles
            if bundle["name"] == studio_bundle_name
        ),
        None
    )

    if studio_bundle is None:
        raise RuntimeError(f"Failed to find bundle '{studio_bundle_name}'.")

    project_bundle = None
    if project_bundle_name and project_bundle_name != studio_bundle_name:
        project_bundle = next(
            (
                bundle
                for bundle in bundles
                if bundle["name"] == project_bundle_name
            ),
            None
        )

        if project_bundle is None:
            raise RuntimeError(
                f"Failed to find project bundle '{project_bundle_name}'."
            )

    return studio_bundle, project_bundle


@dataclass(frozen=True)
class BundleAddon:
    name: str
    version: str


@dataclass(frozen=True)
class BundleInformation:
    studio_bundle: dict[str, Any]
    project_bundle: dict[str, Any] | None
    addons: list[BundleAddon]


def _load_bundle_information() -> BundleInformation:
    """Receive information about addons to use from server.

    Todos:
        Actually ask server for the information.
        Allow project name as optional argument to be able to query
            information about used addons for specific project.
        Wrap versions into an object.

    Returns:
        BundleInformation: List of addon information to use.

    """
    studio_bundle, project_bundle = _get_ayon_bundle_data()
    key_values = {
        "summary": "true",
        "bundle_name": studio_bundle["name"],
    }
    if project_bundle:
        key_values["project_bundle_name"] = project_bundle["name"]

    query = urlencode(key_values)

    response = ayon_api.get(f"settings?{query}")
    addons = [
        BundleAddon(name=addon["name"], version=addon["version"])
        for addon in response.data["addons"]
    ]

    _LoadCache.bundle_information = BundleInformation(
        studio_bundle=studio_bundle,
        project_bundle=project_bundle,
        addons=addons,
    )
    return _LoadCache.bundle_information


def _load_ayon_addons(
    bundle_info: BundleInformation,
) -> list[ModuleType]:
    """Load AYON addons based on information from server.

    This function should not trigger downloading of any addons but only use
    what is already available on the machine (at least in first stages of
    development).

    Args:
        bundle_info (BundleInformation): Bundle information.

    Returns:
        list[ModuleType]: Loaded addon modules.

    """
    log = Logger.get_logger("AddonsLoader")
    _LoadCache.addon_modules = []
    if not bundle_info.addons:
        return _LoadCache.addon_modules

    addons_dir = os.environ.get("AYON_ADDONS_DIR")
    if not addons_dir:
        addons_dir = get_launcher_storage_dir("addons")

    dev_mode_enabled = is_dev_mode_enabled()
    dev_addons_info = {}
    if dev_mode_enabled:
        # Get dev addons info only when dev mode is enabled
        dev_addons_info = bundle_info.studio_bundle.get(
            "addonDevelopment", dev_addons_info
        )

    addons_dir_exists = os.path.exists(addons_dir)
    if not addons_dir_exists:
        log.warning(
            f"Addons directory does not exists. Path \"{addons_dir}\"")

    for addon in bundle_info.addons:
        addon_name = addon.name
        addon_version = addon.version
        # core addon does not have any addon object
        if addon_name == "core":
            continue

        dev_addon_info = dev_addons_info.get(addon_name, {})
        use_dev_path = dev_addon_info.get("enabled", False)

        addon_dir = None
        if use_dev_path:
            addon_dir = dev_addon_info["path"]
            if addon_dir:
                addon_dir = os.path.expandvars(
                    addon_dir.format_map(os.environ)
                )

            if not addon_dir or not os.path.exists(addon_dir):
                log.warning(
                    f"Dev addon {addon_name} {addon_version} path"
                    f" does not exists. Path \"{addon_dir}\""
                )
                continue

        elif addons_dir_exists:
            folder_name = f"{addon_name}_{addon_version}"
            addon_dir = os.path.join(addons_dir, folder_name)
            if not os.path.exists(addon_dir):
                log.debug(
                    "No localized client code found"
                    f" for addon {addon_name} {addon_version}."
                )
                continue

        if not addon_dir:
            continue

        sys.path.insert(0, addon_dir)
        addon_modules = []
        for name in os.listdir(addon_dir):
            # Ignore of files is implemented to be able to run code from code
            #   where usually is more files than just the addon
            # Ignore start and setup scripts
            if name in ("setup.py", "start.py", "__pycache__"):
                continue

            path = os.path.join(addon_dir, name)
            basename, ext = os.path.splitext(name)
            # Ignore folders/files with dot in name
            #   - dot names cannot be imported in Python
            if "." in basename:
                continue
            is_dir = os.path.isdir(path)
            is_py_file = ext.lower() == ".py"
            if not is_py_file and not is_dir:
                continue

            try:
                mod = __import__(basename, fromlist=("",))
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, AYONAddon)
                    ):
                        addon_modules.append(mod)
                        break

            except BaseException:
                log.warning(
                    f"Failed to import \"{basename}\"",
                    exc_info=True
                )

        if not addon_modules:
            log.warning(
                f"Addon {addon_name} {addon_version} has no content to import"
            )
            continue

        if len(addon_modules) > 1:
            joined_modules = ", ".join([m.__name__ for m in addon_modules])
            log.warning(
                f"Multiple modules ({joined_modules}) were found in"
                f" addon '{addon_name}' in dir {addon_dir}."
            )
        _LoadCache.addon_modules.extend(addon_modules)

    return _LoadCache.addon_modules


class _LoadCache:
    lock = threading.Lock()
    loaded = False
    bundle_information = None
    addon_modules = []


def load_addons(force: bool = False) -> None:
    """Load AYON addons as python modules.

    Modules does not load only classes (like in Interfaces) because there must
    be ability to use inner code of addon and be able to import it from one
    defined place.

    With this it is possible to import addon's content from predefined module.

    Args:
        force (bool): Force to load addons even if are already loaded.
            This won't update already loaded and used (cached) modules.

    """
    _cache_data(force=force)


def get_bundle_information() -> BundleInformation:
    _cache_data()
    return _LoadCache.bundle_information


def _cache_data(force: bool = False) -> None:
    if _LoadCache.loaded and not force:
        return

    if not _LoadCache.lock.locked():
        with _LoadCache.lock:
            _load_bundle_information()
            _load_ayon_addons(_LoadCache.bundle_information)
            _LoadCache.loaded = True
    else:
        # If lock is locked wait until is finished
        while _LoadCache.lock.locked():
            time.sleep(0.1)


class AYONAddon(ABC):
    """Base class of AYON addon.

    Attributes:
        enabled (bool): Is addon enabled.

    Args:
        manager (AddonsManager): Manager object who discovered addon.
        settings (dict[str, Any]): AYON settings.

    """
    enabled: bool = True
    _id = None

    # Temporary variable for 'version' property
    _missing_version_warned = False

    def __init__(
        self, manager: AddonsManager, settings: dict[str, Any]
    ) -> None:
        self.manager = manager

        self.log = Logger.get_logger(self.name)

        self.initialize(settings)

    @property
    def id(self) -> str:
        """Random id of addon object.

        Returns:
            str: Object id.

        """
        if self._id is None:
            self._id = uuid4()
        return self._id

    @property
    @abstractmethod
    def name(self) -> str:
        """Addon name.

        Returns:
            str: Addon name.

        """
        pass

    @property
    def version(self) -> str:
        """Addon version.

        Todo:
            Should be abstract property (required). Introduced in
                ayon-core 0.3.3 .

        Returns:
            str: Addon version as semver compatible string.

        """
        if not self.__class__._missing_version_warned:
            self.__class__._missing_version_warned = True
            print(
                f"DEV WARNING: Addon '{self.name}' does not have"
                f" defined version."
            )
        return "0.0.0"

    def initialize(self, settings: dict[str, Any]) -> None:
        """Initialization of addon attributes.

        It is not recommended to override __init__ that's why specific method
        was implemented.

        Args:
            settings (dict[str, Any]): Settings.

        """
        pass

    def connect_with_addons(self, enabled_addons: list[AYONAddon]) -> None:
        """Connect with other enabled addons.

        Args:
            enabled_addons (list[AYONAddon]): Addons that are enabled.

        """
        pass

    def ensure_is_process_ready(
        self, process_context: ProcessContext
    ) -> None:
        """Make sure addon is prepared for a process.

        This method is called when some action makes sure that addon has set
        necessary data. For example if user should be logged in
        and filled credentials in environment variables this method should
        ask user for credentials.

        Implementation of this method is optional.

        Note:
            The logic can be similar to logic in tray, but tray does not
                require to be logged in.

        Args:
            process_context (ProcessContext): Context of child
                process.

        """
        pass

    def get_global_environments(self) -> dict[str, str]:
        """Get global environments values of addon.

        Environment variables that can be get only from system settings.

        Returns:
            dict[str, str]: Environment variables.

        """
        return {}

    def on_host_install(
        self,
        host: HostBase,
        host_name: str,
        project_name: str,
    ) -> None:
        """Host was installed which gives option to handle in-host logic.

        It is a good option to register in-host event callbacks which are
        specific for the addon. The addon is kept in memory for rest of
        the process.

        Arguments may change in future. E.g. 'host_name' should be possible
        to receive from 'host' object.

        Args:
            host (HostBase): Access to installed/registered
                host object.
            host_name (str): Name of host.
            project_name (str): Project name which is main part of host
                context.

        """
        pass

    def cli(self, addon_click_group: click.Group) -> None:
        """Add commands to click group.

        The best practise is to create click group for whole addon which is
        used to separate commands.

        Example:
            class MyPlugin(AYONAddon):
                ...
                def cli(self, addon_click_group):
                    addon_click_group.add_command(cli_main)


            @click.group(<addon name>, help="<Any help shown in cmd>")
            def cli_main():
                pass

            @cli_main.command()
            def mycommand():
                print("my_command")

        Args:
            addon_click_group (click.Group): Group to which can be added
                commands.

        """
        pass


@dataclass
class _ReportRow:
    name: str
    version: str
    server_version: str | None
    server_addon: bool = False
    init_time: float = 0.0
    connect_time: float = 0.0
    tray_init_time: float = 0.0
    tray_menu_time: float = 0.0
    tray_start_time: float = 0.0
    total_time: float = 0.0

    def sum_total(self) -> None:
        self.total_time = (
            self.init_time
            + self.connect_time
            + self.tray_init_time
            + self.tray_menu_time
            + self.tray_start_time
        )


class AddonsManager:
    """Manager of addons that helps to load and prepare them to work.

    Args:
        settings (dict[str, Any] | None): AYON studio settings.
        initialize (bool): Initialize addons on init.
            True by default.

    """
    # Helper attributes for report
    _log = None

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        initialize: bool = True,
    ) -> None:
        self._settings = settings

        self._addons: list[AYONAddon] = []
        self._addons_by_id: dict[str, AYONAddon] = {}
        self._addons_by_name: dict[str, AYONAddon] = {}
        self._report_by_name: dict[str, _ReportRow] = {}
        self._total_row: _ReportRow = _ReportRow("Total", "(0)", "(0)")

        if initialize:
            self.initialize_addons()
            self.connect_addons()

    def __getitem__(self, addon_name: str) -> AYONAddon:
        return self._addons_by_name[addon_name]

    @property
    def log(self) -> logging.Logger:
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    def get(
        self, addon_name: str, default: Any | None = None
    ) -> AYONAddon | Any:
        """Access addon by name.

        Args:
            addon_name (str): Name of addon which should be returned.
            default (Any | None): Default output if addon is not available.

        Returns:
            AYONAddon | Any: Addon found by name or `default`.

        """
        return self._addons_by_name.get(addon_name, default)

    @property
    def addons(self) -> list[AYONAddon]:
        return list(self._addons)

    @property
    def addons_by_id(self) -> dict[str, AYONAddon]:
        return dict(self._addons_by_id)

    @property
    def addons_by_name(self) -> dict[str, AYONAddon]:
        return dict(self._addons_by_name)

    def get_enabled_addon(
        self, addon_name: str, default: Any | None = None
    ) -> AYONAddon | Any:
        """Fast access to enabled addon.

        If addon is available but is not enabled default value is returned.

        Args:
            addon_name (str): Name of addon which should be returned.
            default (Any): Default output if addon is not available or is
                not enabled.

        Returns:
            Union[AYONAddon, Any]: Enabled addon found by name or None.

        """
        addon = self.get(addon_name)
        if addon is not None and addon.enabled:
            return addon
        return default

    def get_enabled_addons(self) -> list[AYONAddon]:
        """Enabled addons initialized by the manager.

        Returns:
            list[AYONAddon]: Initialized and enabled addons.

        """
        return [
            addon
            for addon in self._addons
            if addon.enabled
        ]

    def initialize_addons(self) -> None:
        """Import and initialize addons."""
        # Make sure modules are loaded
        load_addons()

        self.log.debug("AYON addons initialization.")

        # Prepare settings for addons
        settings = self._settings
        if settings is None:
            settings = get_studio_settings()

        time_start = time.time()
        prev_start_time = time_start
        addon_classes = []
        for module in _LoadCache.addon_modules:
            # Go through globals in `ayon_core.modules`
            for name in dir(module):
                modules_item = getattr(module, name, None)
                # Filter globals that are not classes which inherit from
                #   AYONAddon
                if (
                    not inspect.isclass(modules_item)
                    or modules_item is AYONAddon
                    or not issubclass(modules_item, AYONAddon)
                ):
                    continue

                # Check if class is abstract (Developing purpose)
                if inspect.isabstract(modules_item):
                    # Find abstract attributes by convention on `abc` module
                    not_implemented = []
                    for attr_name in dir(modules_item):
                        attr = getattr(modules_item, attr_name, None)
                        abs_method = getattr(
                            attr, "__isabstractmethod__", None
                        )
                        if attr and abs_method:
                            not_implemented.append(attr_name)

                    # Log missing implementations
                    self.log.warning((
                        "Skipping abstract Class: {}."
                        " Missing implementations: {}"
                    ).format(name, ", ".join(not_implemented)))
                    continue

                addon_classes.append(modules_item)

        bundle_info = get_bundle_information()
        server_version_by_name = {
            addon.name: addon.version
            for addon in bundle_info.addons
        }
        server_addons = set(server_version_by_name)
        server_addons.discard("core")
        self._report_by_name["core"] = _ReportRow(
            name="core",
            version=__version__,
            server_version=server_version_by_name.get("core"),
        )
        for addon_cls in addon_classes:
            name = addon_cls.__name__
            try:
                addon = addon_cls(self, settings)
                server_version = server_version_by_name.get(addon.name)
                report_row = _ReportRow(
                    name=addon.name,
                    version=addon.version,
                    server_version=server_version,
                )
                # Store initialized object
                self._addons.append(addon)
                self._addons_by_id[addon.id] = addon
                self._addons_by_name[addon.name] = addon
                self._report_by_name[addon.name] = report_row
                server_addons.discard(addon.name)

                now = time.time()
                report_row.init_time = now - prev_start_time
                prev_start_time = now

            except Exception:
                self.log.warning(
                    "Initialization of addon '{}' failed.".format(name),
                    exc_info=True
                )

        self._total_row.version = f"({len(self._report_by_name)})"
        self._total_row.server_version = f"({len(server_version_by_name)})"

        for addon_name in server_addons:
            self._report_by_name[addon_name] = _ReportRow(
                name=addon_name,
                version="-",
                server_version=server_version_by_name[addon_name],
                server_addon=True,
            )

        for addon_name in sorted(self._addons_by_name.keys()):
            addon = self._addons_by_name[addon_name]
            enabled_str = "X" if addon.enabled else " "
            self.log.debug(
                f"[{enabled_str}] {addon.name} ({addon.version})"
            )

        self._total_row.init_time = time.time() - time_start

    def connect_addons(self) -> None:
        """Trigger connection with other enabled addons.

        Addons should handle their interfaces in `connect_with_addons`.
        """
        time_start = time.time()
        prev_start_time = time_start
        enabled_addons = self.get_enabled_addons()
        self.log.debug(f"Has {len(enabled_addons)} enabled addons.")
        for addon in enabled_addons:
            report_row = self._report_by_name[addon.name]
            try:
                addon.connect_with_addons(enabled_addons)

            except Exception:
                self.log.error(
                    "BUG: Module failed on connection with other modules.",
                    exc_info=True
                )

            now = time.time()
            report_row.connect_time = now - prev_start_time
            prev_start_time = now

        self._total_row.connect_time = time.time() - time_start

    def collect_global_environments(self) -> dict[str, str]:
        """Helper to collect global environment variabled from modules.

        Returns:
            dict: Global environment variables from enabled modules.

        Raises:
            AssertionError: Global environment variables must be unique for
                all modules.
        """
        module_envs = {}
        for module in self.get_enabled_addons():
            # Collect global module's global environments
            _envs = module.get_global_environments()
            for key, value in _envs.items():
                if key in module_envs:
                    # TODO better error message
                    raise AssertionError(
                        "Duplicated environment key {}".format(key)
                    )
                module_envs[key] = value
        return module_envs

    def collect_plugin_paths(self) -> dict[str, list[str]]:
        """Helper to collect all plugins from modules inherited IPluginPaths.

        Unknown keys are logged out.

        Deprecated:
            Use targeted methods 'collect_launcher_action_paths',
                'collect_create_plugin_paths', 'collect_load_plugin_paths',
                'collect_publish_plugin_paths' and
                 'collect_inventory_action_paths' to collect plugin paths.

        Returns:
            dict: Output is dictionary with keys "publish", "create", "load",
                "actions" and "inventory" each containing list of paths.

        """
        warnings.warn(
            "Used deprecated method 'collect_plugin_paths'. Please use"
            " targeted methods 'collect_launcher_action_paths',"
            " 'collect_create_plugin_paths', 'collect_load_plugin_paths'"
            " 'collect_publish_plugin_paths' and"
            " 'collect_inventory_action_paths'",
            DeprecationWarning,
            stacklevel=2
        )
        # Output structure
        output = {
            "publish": [],
            "create": [],
            "load": [],
            "actions": [],
            "inventory": []
        }
        unknown_keys_by_addon = {}
        for addon in self.get_enabled_addons():
            # Skip module that do not inherit from `IPluginPaths`
            if not isinstance(addon, IPluginPaths):
                continue
            plugin_paths = addon.get_plugin_paths()
            for key, value in plugin_paths.items():
                # Filter unknown keys
                if key not in output:
                    if addon.name not in unknown_keys_by_addon:
                        unknown_keys_by_addon[addon.name] = []
                    unknown_keys_by_addon[addon.name].append(key)
                    continue

                # Skip if value is empty
                if not value:
                    continue

                # Convert to list if value is not list
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                output[key].extend(value)

        # Report unknown keys (Developing purposes)
        if unknown_keys_by_addon:
            expected_keys = ", ".join([
                f'"{key}"' for key in output.keys()
            ])
            msg_items = []
            for addon_name, keys in unknown_keys_by_addon.items():
                joined_keys = ", ".join([f'"{key}"' for key in keys])
                msg_items.append(
                    f"Addon: \"{addon_name}\" - got key {joined_keys}"
                )
            joined_items = " | ".join(msg_items)
            self.log.warning(
                f"Expected keys from `get_plugin_paths` are {expected_keys}."
                f" {joined_items}"
            )
        return output

    def _collect_plugin_paths(self, method_name: str, *args, **kwargs):
        output = []
        for addon in self.get_enabled_addons():
            # Skip addon that do not inherit from `IPluginPaths`
            if not isinstance(addon, IPluginPaths):
                continue

            paths = None
            method = getattr(addon, method_name)
            try:
                paths = method(*args, **kwargs)
            except Exception:
                self.log.warning(
                    "Failed to get plugin paths from addon"
                    f" '{addon.name}' using '{method_name}'.",
                    exc_info=True
                )

            if not paths:
                continue

            if isinstance(paths, str):
                paths = [paths]
                self.log.warning(
                    f"Addon '{addon.name}' returned invalid output type"
                    f" from '{method_name}'."
                    f" Got 'str' expected 'list[str]'."
                )
            output.extend(paths)
        return output

    def collect_launcher_action_paths(self) -> list[str]:
        """Helper to collect launcher action paths from addons.

        Returns:
            list: List of paths to launcher actions.

        """
        output = self._collect_plugin_paths(
            "get_launcher_action_paths"
        )
        # Add default core actions
        actions_dir = os.path.join(AYON_CORE_ROOT, "plugins", "actions")
        output.insert(0, actions_dir)
        return output

    def collect_create_plugin_paths(self, host_name: str) -> list[str]:
        """Helper to collect creator plugin paths from addons.

        Args:
            host_name (str): For which host are creators meant.

        Returns:
            list[str]: List of creator plugin paths.

        """
        return self._collect_plugin_paths(
            "get_create_plugin_paths",
            host_name
        )

    collect_creator_plugin_paths = collect_create_plugin_paths

    def collect_load_plugin_paths(self, host_name: str) -> list[str]:
        """Helper to collect load plugin paths from addons.

        Args:
            host_name (str): For which host are load plugins meant.

        Returns:
            list[str]: List of load plugin paths.

        """
        return self._collect_plugin_paths(
            "get_load_plugin_paths",
            host_name
        )

    def collect_publish_plugin_paths(self, host_name: str) -> list[str]:
        """Helper to collect load plugin paths from addons.

        Args:
            host_name (str): For which host are load plugins meant.

        Returns:
            list[str]: List of pyblish plugin paths.

        """
        return self._collect_plugin_paths(
            "get_publish_plugin_paths",
            host_name
        )

    def collect_inventory_action_paths(self, host_name: str) -> list[str]:
        """Helper to collect load plugin paths from addons.

        Args:
            host_name (str): For which host are load plugins meant.

        Returns:
            list: List of pyblish plugin paths.

        """
        return self._collect_plugin_paths(
            "get_inventory_action_paths",
            host_name
        )

    def get_host_addon(self, host_name: str) -> IHostAddon | None:
        """Find host addon by host name.

        Args:
            host_name (str): Host name for which is found host addon.

        Returns:
            IHostAddon | None: Found host addon by name or `None`.
        """

        for addon in self.get_enabled_addons():
            if (
                isinstance(addon, IHostAddon)
                and addon.host_name == host_name
            ):
                return addon
        return None

    def get_host_names(self) -> set[str]:
        """List of available host names based on host addons.

        Returns:
            set[str]: All available host names based on enabled addons
                inheriting 'IHostAddon'.

        """
        return {
            addon.host_name
            for addon in self.get_enabled_addons()
            if isinstance(addon, IHostAddon)
        }

    def print_report(self, include_tray: bool = False) -> None:
        """Print out report of time spent on addons initialization parts.

        Reporting is not automated must be implemented for each initialization
        part separately. Reports must be stored to `_report` attribute.
        Print is skipped if `_report` is empty.

        Attribute `_report` is dictionary where key is "label" describing
        the processed part and value is dictionary where key is addon's
        class name and value is time delta of it's processing.

        """
        sorted_rows = [
            report_row
            for report_row in sorted(
                self._report_by_name.values(),
                key=lambda item: item.name
            )
        ]
        sorted_rows.append(self._total_row)
        for report_row in sorted_rows:
            report_row.sum_total()

        # Add addon names to first column
        names = [row.name for row in sorted_rows]
        names.insert(0, "Addon name")
        versions = [row.version or "N/A" for row in sorted_rows]
        versions.insert(0, "Version")
        server_versions = [
            row.server_version or "N/A" for row in sorted_rows
        ]
        server_versions.insert(0, "Server v.")

        # Prepare columns to calculate their widths
        cols: list[list[str]] = [names, versions, server_versions]
        for col_name, attr_name, is_tray_value in (
            ("Initialize", "init_time", False),
            ("Connect", "connect_time", False),
            ("Tray init", "tray_init_time", True),
            ("Tray menu", "tray_menu_time", True),
            ("Startup", "tray_start_time", True),
            ("Total", "total_time", False),
        ):
            if is_tray_value and not include_tray:
                continue

            values = [
                f"{getattr(row, attr_name):.3f}"
                for row in sorted_rows
            ]
            values.insert(0, col_name)
            cols.append(values)

        col_widths = [
            max((len(value) for value in col_values))
            for col_values in cols
        ]

        # Convert columns to rows for print
        rows = list(zip(*cols))
        # Top row contains labels
        top_row = rows.pop(0)
        # Last row contains totals
        total_row = rows.pop(-1)

        separator = "+".join([w * "-" for w in col_widths])

        lines = [separator]
        lines.append("|".join(
            value.ljust(col_width)
            for col_width, value in zip(col_widths, top_row)
        ))
        lines.append(separator)

        for row in rows:
            lines.append("|".join(
                value.ljust(col_width)
                for col_width, value in zip(col_widths, row)
            ))

        lines.append(separator)
        lines.append("|".join(
            value.ljust(col_width)
            for col_width, value in zip(col_widths, total_row)
        ))
        lines.append("")

        output = "\n".join(lines)
        print(output)
