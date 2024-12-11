# -*- coding: utf-8 -*-
"""Base class for AYON addons."""
import copy
import os
import sys
import time
import inspect
import logging
import threading
import collections
from uuid import uuid4
from abc import ABC, abstractmethod
from typing import Optional

import ayon_api
from semver import VersionInfo

from ayon_core import AYON_CORE_ROOT
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

# Files that will be always ignored on addons import
IGNORED_FILENAMES = {
    "__pycache__",
}
# Files ignored on addons import from "./ayon_core/modules"
IGNORED_DEFAULT_FILENAMES = {
    "__init__.py",
}

# When addon was moved from ayon-core codebase
# - this is used to log the missing addon
MOVED_ADDON_MILESTONE_VERSIONS = {
    "aftereffects": VersionInfo(0, 2, 0),
    "applications": VersionInfo(0, 2, 0),
    "blender": VersionInfo(0, 2, 0),
    "celaction": VersionInfo(0, 2, 0),
    "clockify": VersionInfo(0, 2, 0),
    "deadline": VersionInfo(0, 2, 0),
    "flame": VersionInfo(0, 2, 0),
    "fusion": VersionInfo(0, 2, 0),
    "harmony": VersionInfo(0, 2, 0),
    "hiero": VersionInfo(0, 2, 0),
    "max": VersionInfo(0, 2, 0),
    "photoshop": VersionInfo(0, 2, 0),
    "timers_manager": VersionInfo(0, 2, 0),
    "traypublisher": VersionInfo(0, 2, 0),
    "tvpaint": VersionInfo(0, 2, 0),
    "maya": VersionInfo(0, 2, 0),
    "nuke": VersionInfo(0, 2, 0),
    "resolve": VersionInfo(0, 2, 0),
    "royalrender": VersionInfo(0, 2, 0),
    "substancepainter": VersionInfo(0, 2, 0),
    "houdini": VersionInfo(0, 3, 0),
    "unreal": VersionInfo(0, 2, 0),
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
        project_name (Optional[str]): Project name. Can be filled in case
            process is triggered for specific project. Some addons can have
            different behavior based on project. Value is NOT autofilled.
        headless (Optional[bool]): Is process running in headless mode. Value
            is filled with value based on state set in AYON launcher.

    """
    def __init__(
        self,
        addon_name: str,
        addon_version: str,
        project_name: Optional[str] = None,
        headless: Optional[bool] = None,
        **kwargs,
    ):
        if headless is None:
            headless = is_headless_mode_enabled()
        self.addon_name: str = addon_name
        self.addon_version: str = addon_version
        self.project_name: Optional[str] = project_name
        self.headless: bool = headless

        if kwargs:
            unknown_keys = ", ".join([f'"{key}"' for key in kwargs.keys()])
            print(f"Unknown keys in ProcessContext: {unknown_keys}")


class _LoadCache:
    addons_lock = threading.Lock()
    addons_loaded = False
    addon_modules = []


def load_addons(force=False):
    """Load AYON addons as python modules.

    Modules does not load only classes (like in Interfaces) because there must
    be ability to use inner code of addon and be able to import it from one
    defined place.

    With this it is possible to import addon's content from predefined module.

    Args:
        force (bool): Force to load addons even if are already loaded.
            This won't update already loaded and used (cached) modules.
    """

    if _LoadCache.addons_loaded and not force:
        return

    if not _LoadCache.addons_lock.locked():
        with _LoadCache.addons_lock:
            _load_addons()
            _LoadCache.addons_loaded = True
    else:
        # If lock is locked wait until is finished
        while _LoadCache.addons_lock.locked():
            time.sleep(0.1)


def _get_ayon_bundle_data():
    bundles = ayon_api.get_bundles()["bundles"]

    bundle_name = os.getenv("AYON_BUNDLE_NAME")

    return next(
        (
            bundle
            for bundle in bundles
            if bundle["name"] == bundle_name
        ),
        None
    )


def _get_ayon_addons_information(bundle_info):
    """Receive information about addons to use from server.

    Todos:
        Actually ask server for the information.
        Allow project name as optional argument to be able to query information
            about used addons for specific project.

    Returns:
        List[Dict[str, Any]]: List of addon information to use.
    """

    output = []
    bundle_addons = bundle_info["addons"]
    addons = ayon_api.get_addons_info()["addons"]
    for addon in addons:
        name = addon["name"]
        versions = addon.get("versions")
        addon_version = bundle_addons.get(name)
        if addon_version is None or not versions:
            continue
        version = versions.get(addon_version)
        if version:
            version = copy.deepcopy(version)
            version["name"] = name
            version["version"] = addon_version
            output.append(version)
    return output


def _handle_moved_addons(addon_name, milestone_version, log):
    """Log message that addon version is not compatible with current core.

    The function can return path to addon client code, but that can happen
        only if ayon-core is used from code (for development), but still
        logs a warning.

    Args:
        addon_name (str): Addon name.
        milestone_version (str): Milestone addon version.
        log (logging.Logger): Logger object.

    Returns:
        Union[str, None]: Addon dir or None.
    """
    # Handle addons which were moved out of ayon-core
    # - Try to fix it by loading it directly from server addons dir in
    #   ayon-core repository. But that will work only if ayon-core is
    #   used from code.
    addon_dir = os.path.join(
        os.path.dirname(os.path.dirname(AYON_CORE_ROOT)),
        "server_addon",
        addon_name,
        "client",
    )
    if not os.path.exists(addon_dir):
        log.error(
            f"Addon '{addon_name}' is not available. Please update "
            f"{addon_name} addon to '{milestone_version}' or higher."
        )
        return None

    log.warning((
        "Please update '{}' addon to '{}' or higher."
        " Using client code from ayon-core repository."
    ).format(addon_name, milestone_version))
    return addon_dir


def _load_ayon_addons(log):
    """Load AYON addons based on information from server.

    This function should not trigger downloading of any addons but only use
    what is already available on the machine (at least in first stages of
    development).

    Args:
        log (logging.Logger): Logger object.

    """
    all_addon_modules = []
    bundle_info = _get_ayon_bundle_data()
    addons_info = _get_ayon_addons_information(bundle_info)
    if not addons_info:
        return all_addon_modules

    addons_dir = os.environ.get("AYON_ADDONS_DIR")
    if not addons_dir:
        addons_dir = get_launcher_storage_dir("addons")

    dev_mode_enabled = is_dev_mode_enabled()
    dev_addons_info = {}
    if dev_mode_enabled:
        # Get dev addons info only when dev mode is enabled
        dev_addons_info = bundle_info.get("addonDevelopment", dev_addons_info)

    addons_dir_exists = os.path.exists(addons_dir)
    if not addons_dir_exists:
        log.warning("Addons directory does not exists. Path \"{}\"".format(
            addons_dir
        ))

    for addon_info in addons_info:
        addon_name = addon_info["name"]
        addon_version = addon_info["version"]

        # core addon does not have any addon object
        if addon_name == "core":
            continue

        dev_addon_info = dev_addons_info.get(addon_name, {})
        use_dev_path = dev_addon_info.get("enabled", False)

        addon_dir = None
        milestone_version = MOVED_ADDON_MILESTONE_VERSIONS.get(addon_name)
        if use_dev_path:
            addon_dir = dev_addon_info["path"]
            if not addon_dir or not os.path.exists(addon_dir):
                log.warning((
                    "Dev addon {} {} path does not exists. Path \"{}\""
                ).format(addon_name, addon_version, addon_dir))
                continue

        elif (
            milestone_version is not None
            and VersionInfo.parse(addon_version) < milestone_version
        ):
            addon_dir = _handle_moved_addons(
                addon_name, milestone_version, log
            )
            if not addon_dir:
                continue

        elif addons_dir_exists:
            folder_name = "{}_{}".format(addon_name, addon_version)
            addon_dir = os.path.join(addons_dir, folder_name)
            if not os.path.exists(addon_dir):
                log.debug((
                    "No localized client code found for addon {} {}."
                ).format(addon_name, addon_version))
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
                    "Failed to import \"{}\"".format(basename),
                    exc_info=True
                )

        if not addon_modules:
            log.warning("Addon {} {} has no content to import".format(
                addon_name, addon_version
            ))
            continue

        if len(addon_modules) > 1:
            log.warning((
                "Multiple modules ({}) were found in addon '{}' in dir {}."
            ).format(
                ", ".join([m.__name__ for m in addon_modules]),
                addon_name,
                addon_dir,
            ))
        all_addon_modules.extend(addon_modules)

    return all_addon_modules


def _load_addons():
    log = Logger.get_logger("AddonsLoader")

    # Store modules to local cache
    _LoadCache.addon_modules = _load_ayon_addons(log)


class AYONAddon(ABC):
    """Base class of AYON addon.

    Attributes:
        enabled (bool): Is addon enabled.
        name (str): Addon name.

    Args:
        manager (AddonsManager): Manager object who discovered addon.
        settings (dict[str, Any]): AYON settings.

    """
    enabled = True
    _id = None

    # Temporary variable for 'version' property
    _missing_version_warned = False

    def __init__(self, manager, settings):
        self.manager = manager

        self.log = Logger.get_logger(self.name)

        self.initialize(settings)

    @property
    def id(self):
        """Random id of addon object.

        Returns:
            str: Object id.

        """
        if self._id is None:
            self._id = uuid4()
        return self._id

    @property
    @abstractmethod
    def name(self):
        """Addon name.

        Returns:
            str: Addon name.

        """
        pass

    @property
    def version(self):
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

    def initialize(self, settings):
        """Initialization of addon attributes.

        It is not recommended to override __init__ that's why specific method
        was implemented.

        Args:
            settings (dict[str, Any]): Settings.

        """
        pass

    def connect_with_addons(self, enabled_addons):
        """Connect with other enabled addons.

        Args:
            enabled_addons (list[AYONAddon]): Addons that are enabled.

        """
        pass

    def ensure_is_process_ready(
        self, process_context: ProcessContext
    ):
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

    def get_global_environments(self):
        """Get global environments values of addon.

        Environment variables that can be get only from system settings.

        Returns:
            dict[str, str]: Environment variables.

        """
        return {}

    def modify_application_launch_arguments(self, application, env):
        """Give option to modify launch environments before application launch.

        Implementation is optional. To change environments modify passed
        dictionary of environments.

        Args:
            application (Application): Application that is launched.
            env (dict[str, str]): Current environment variables.

        """
        pass

    def on_host_install(self, host, host_name, project_name):
        """Host was installed which gives option to handle in-host logic.

        It is a good option to register in-host event callbacks which are
        specific for the addon. The addon is kept in memory for rest of
        the process.

        Arguments may change in future. E.g. 'host_name' should be possible
        to receive from 'host' object.

        Args:
            host (Union[ModuleType, HostBase]): Access to installed/registered
                host object.
            host_name (str): Name of host.
            project_name (str): Project name which is main part of host
                context.

        """
        pass

    def cli(self, addon_click_group):
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


class _AddonReportInfo:
    def __init__(
        self, class_name, name, version, report_value_by_label
    ):
        self.class_name = class_name
        self.name = name
        self.version = version
        self.report_value_by_label = report_value_by_label

    @classmethod
    def from_addon(cls, addon, report):
        class_name = addon.__class__.__name__
        report_value_by_label = {
            label: reported.get(class_name)
            for label, reported in report.items()
        }
        return cls(
            addon.__class__.__name__,
            addon.name,
            addon.version,
            report_value_by_label
        )


class AddonsManager:
    """Manager of addons that helps to load and prepare them to work.

    Args:
        settings (Optional[dict[str, Any]]): AYON studio settings.
        initialize (Optional[bool]): Initialize addons on init.
            True by default.

    """
    # Helper attributes for report
    _report_total_key = "Total"
    _log = None

    def __init__(self, settings=None, initialize=True):
        self._settings = settings

        self._addons = []
        self._addons_by_id = {}
        self._addons_by_name = {}
        # For report of time consumption
        self._report = {}

        if initialize:
            self.initialize_addons()
            self.connect_addons()

    def __getitem__(self, addon_name):
        return self._addons_by_name[addon_name]

    @property
    def log(self):
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    def get(self, addon_name, default=None):
        """Access addon by name.

        Args:
            addon_name (str): Name of addon which should be returned.
            default (Any): Default output if addon is not available.

        Returns:
            Union[AYONAddon, Any]: Addon found by name or `default`.

        """
        return self._addons_by_name.get(addon_name, default)

    @property
    def addons(self):
        return list(self._addons)

    @property
    def addons_by_id(self):
        return dict(self._addons_by_id)

    @property
    def addons_by_name(self):
        return dict(self._addons_by_name)

    def get_enabled_addon(self, addon_name, default=None):
        """Fast access to enabled addon.

        If addon is available but is not enabled default value is returned.

        Args:
            addon_name (str): Name of addon which should be returned.
            default (Any): Default output if addon is not available or is
                not enabled.

        Returns:
            Union[AYONAddon, None]: Enabled addon found by name or None.

        """
        addon = self.get(addon_name)
        if addon is not None and addon.enabled:
            return addon
        return default

    def get_enabled_addons(self):
        """Enabled addons initialized by the manager.

        Returns:
            list[AYONAddon]: Initialized and enabled addons.

        """
        return [
            addon
            for addon in self._addons
            if addon.enabled
        ]

    def initialize_addons(self):
        """Import and initialize addons."""
        # Make sure modules are loaded
        load_addons()

        self.log.debug("*** AYON addons initialization.")

        # Prepare settings for addons
        settings = self._settings
        if settings is None:
            settings = get_studio_settings()

        report = {}
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

        for addon_cls in addon_classes:
            name = addon_cls.__name__
            try:
                addon = addon_cls(self, settings)
                # Store initialized object
                self._addons.append(addon)
                self._addons_by_id[addon.id] = addon
                self._addons_by_name[addon.name] = addon

                now = time.time()
                report[addon.__class__.__name__] = now - prev_start_time
                prev_start_time = now

            except Exception:
                self.log.warning(
                    "Initialization of addon '{}' failed.".format(name),
                    exc_info=True
                )

        for addon_name in sorted(self._addons_by_name.keys()):
            addon = self._addons_by_name[addon_name]
            enabled_str = "X" if addon.enabled else " "
            self.log.debug(
                f"[{enabled_str}] {addon.name} ({addon.version})"
            )

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Initialization"] = report

    def connect_addons(self):
        """Trigger connection with other enabled addons.

        Addons should handle their interfaces in `connect_with_addons`.
        """
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        enabled_addons = self.get_enabled_addons()
        self.log.debug("Has {} enabled addons.".format(len(enabled_addons)))
        for addon in enabled_addons:
            try:
                addon.connect_with_addons(enabled_addons)

            except Exception:
                self.log.error(
                    "BUG: Module failed on connection with other modules.",
                    exc_info=True
                )

            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Connect modules"] = report

    def collect_global_environments(self):
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

    def collect_plugin_paths(self):
        """Helper to collect all plugins from modules inherited IPluginPaths.

        Unknown keys are logged out.

        Returns:
            dict: Output is dictionary with keys "publish", "create", "load",
                "actions" and "inventory" each containing list of paths.
        """
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
                "\"{}\"".format(key) for key in output.keys()
            ])
            msg_template = "Addon: \"{}\" - got key {}"
            msg_items = []
            for addon_name, keys in unknown_keys_by_addon.items():
                joined_keys = ", ".join([
                    "\"{}\"".format(key) for key in keys
                ])
                msg_items.append(msg_template.format(addon_name, joined_keys))
            self.log.warning((
                "Expected keys from `get_plugin_paths` are {}. {}"
            ).format(expected_keys, " | ".join(msg_items)))
        return output

    def _collect_plugin_paths(self, method_name, *args, **kwargs):
        output = []
        for addon in self.get_enabled_addons():
            # Skip addon that do not inherit from `IPluginPaths`
            if not isinstance(addon, IPluginPaths):
                continue

            method = getattr(addon, method_name)
            try:
                paths = method(*args, **kwargs)
            except Exception:
                self.log.warning(
                    (
                        "Failed to get plugin paths from addon"
                        " '{}' using '{}'."
                    ).format(addon.__class__.__name__, method_name),
                    exc_info=True
                )
                continue

            if paths:
                # Convert to list if value is not list
                if not isinstance(paths, (list, tuple, set)):
                    paths = [paths]
                output.extend(paths)
        return output

    def collect_create_plugin_paths(self, host_name):
        """Helper to collect creator plugin paths from addons.

        Args:
            host_name (str): For which host are creators meant.

        Returns:
            list: List of creator plugin paths.
        """

        return self._collect_plugin_paths(
            "get_create_plugin_paths",
            host_name
        )

    collect_creator_plugin_paths = collect_create_plugin_paths

    def collect_load_plugin_paths(self, host_name):
        """Helper to collect load plugin paths from addons.

        Args:
            host_name (str): For which host are load plugins meant.

        Returns:
            list: List of load plugin paths.
        """

        return self._collect_plugin_paths(
            "get_load_plugin_paths",
            host_name
        )

    def collect_publish_plugin_paths(self, host_name):
        """Helper to collect load plugin paths from addons.

        Args:
            host_name (str): For which host are load plugins meant.

        Returns:
            list: List of pyblish plugin paths.
        """

        return self._collect_plugin_paths(
            "get_publish_plugin_paths",
            host_name
        )

    def collect_inventory_action_paths(self, host_name):
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

    def get_host_addon(self, host_name):
        """Find host addon by host name.

        Args:
            host_name (str): Host name for which is found host addon.

        Returns:
            Union[AYONAddon, None]: Found host addon by name or `None`.
        """

        for addon in self.get_enabled_addons():
            if (
                isinstance(addon, IHostAddon)
                and addon.host_name == host_name
            ):
                return addon
        return None

    def get_host_names(self):
        """List of available host names based on host addons.

        Returns:
            Iterable[str]: All available host names based on enabled addons
                inheriting 'IHostAddon'.
        """

        return {
            addon.host_name
            for addon in self.get_enabled_addons()
            if isinstance(addon, IHostAddon)
        }

    def print_report(self):
        """Print out report of time spent on addons initialization parts.

        Reporting is not automated must be implemented for each initialization
        part separately. Reports must be stored to `_report` attribute.
        Print is skipped if `_report` is empty.

        Attribute `_report` is dictionary where key is "label" describing
        the processed part and value is dictionary where key is addon's
        class name and value is time delta of it's processing.

        It is good idea to add total time delta on processed part under key
        which is defined in attribute `_report_total_key`. By default has value
        `"Total"` but use the attribute please.

        ```javascript
        {
            "Initialization": {
                "FtrackAddon": 0.003,
                ...
                "Total": 1.003,
            },
            ...
        }
        ```
        """

        if not self._report:
            return

        available_col_names = set()
        for addon_names in self._report.values():
            available_col_names |= set(addon_names.keys())

        # Prepare ordered dictionary for columns
        addons_info = [
            _AddonReportInfo.from_addon(addon, self._report)
            for addon in self.addons
            if addon.__class__.__name__ in available_col_names
        ]
        addons_info.sort(key=lambda x: x.name)

        addon_name_rows = [
            addon_info.name
            for addon_info in addons_info
        ]
        addon_version_rows = [
            addon_info.version
            for addon_info in addons_info
        ]

        # Add total key (as last addon)
        addon_name_rows.append(self._report_total_key)
        addon_version_rows.append(f"({len(addons_info)})")

        cols = collections.OrderedDict()
        # Add addon names to first columnt
        cols["Addon name"] = addon_name_rows
        cols["Version"] = addon_version_rows

        # Add columns from report
        total_by_addon = {
            row: 0
            for row in addon_name_rows
        }
        for label in self._report.keys():
            rows = []
            col_total = 0
            for addon_info in addons_info:
                value = addon_info.report_value_by_label.get(label)
                if value is None:
                    rows.append("N/A")
                    continue
                rows.append("{:.3f}".format(value))
                total_by_addon[addon_info.name] += value
                col_total += value
            total_by_addon[self._report_total_key] += col_total
            rows.append("{:.3f}".format(col_total))
            cols[label] = rows
        # Add to also total column that should sum the row
        cols[self._report_total_key] = [
            "{:.3f}".format(total_by_addon[addon_name])
            for addon_name in cols["Addon name"]
        ]

        # Prepare column widths and total row count
        # - column width is by
        col_widths = {}
        total_rows = None
        for key, values in cols.items():
            if total_rows is None:
                total_rows = 1 + len(values)
            max_width = len(key)
            for value in values:
                value_length = len(value)
                if value_length > max_width:
                    max_width = value_length
            col_widths[key] = max_width

        rows = []
        for _idx in range(total_rows):
            rows.append([])

        for key, values in cols.items():
            width = col_widths[key]
            idx = 0
            rows[idx].append(key.ljust(width))
            for value in values:
                idx += 1
                rows[idx].append(value.ljust(width))

        filler_parts = []
        for width in col_widths.values():
            filler_parts.append(width * "-")
        filler = "+".join(filler_parts)

        formatted_rows = [filler]
        last_row_idx = len(rows) - 1
        for idx, row in enumerate(rows):
            # Add filler before last row
            if idx == last_row_idx:
                formatted_rows.append(filler)

            formatted_rows.append("|".join(row))

            # Add filler after first row
            if idx == 0:
                formatted_rows.append(filler)

        # Join rows with newline char and add new line at the end
        output = "\n".join(formatted_rows) + "\n"
        print(output)
