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
from abc import ABCMeta, abstractmethod

import six
import appdirs
import ayon_api

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import Logger, is_dev_mode_enabled
from ayon_core.settings import get_studio_settings

from .interfaces import (
    IPluginPaths,
    IHostAddon,
    ITrayAddon,
    ITrayService
)

# Files that will be always ignored on addons import
IGNORED_FILENAMES = (
    "__pycache__",
)
# Files ignored on addons import from "./ayon_core/modules"
IGNORED_DEFAULT_FILENAMES = (
    "__init__.py",
    "base.py",
    "interfaces.py",
    "click_wrap.py",
    "example_addons",
    "default_modules",
)
IGNORED_HOSTS_IN_AYON = {
    "flame",
    "harmony",
}
IGNORED_MODULES_IN_AYON = set()


# Inherit from `object` for Python 2 hosts
class _ModuleClass(object):
    """Fake module class for storing AYON addons.

    Object of this class can be stored to `sys.modules` and used for storing
    dynamically imported modules.
    """

    def __init__(self, name):
        # Call setattr on super class
        super(_ModuleClass, self).__setattr__("name", name)
        super(_ModuleClass, self).__setattr__("__name__", name)

        # Where modules and interfaces are stored
        super(_ModuleClass, self).__setattr__("__attributes__", dict())
        super(_ModuleClass, self).__setattr__("__defaults__", set())

        super(_ModuleClass, self).__setattr__("_log", None)

    def __getattr__(self, attr_name):
        if attr_name not in self.__attributes__:
            if attr_name in ("__path__", "__file__"):
                return None
            raise AttributeError("'{}' has not attribute '{}'".format(
                self.name, attr_name
            ))
        return self.__attributes__[attr_name]

    def __iter__(self):
        for module in self.values():
            yield module

    def __setattr__(self, attr_name, value):
        if attr_name in self.__attributes__:
            self.log.warning(
                "Duplicated name \"{}\" in {}. Overriding.".format(
                    attr_name, self.name
                )
            )
        self.__attributes__[attr_name] = value

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    @property
    def log(self):
        if self._log is None:
            super(_ModuleClass, self).__setattr__(
                "_log", Logger.get_logger(self.name)
            )
        return self._log

    def get(self, key, default=None):
        return self.__attributes__.get(key, default)

    def keys(self):
        return self.__attributes__.keys()

    def values(self):
        return self.__attributes__.values()

    def items(self):
        return self.__attributes__.items()


class _LoadCache:
    addons_lock = threading.Lock()
    addons_loaded = False


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


def _load_ayon_addons(openpype_modules, modules_key, log):
    """Load AYON addons based on information from server.

    This function should not trigger downloading of any addons but only use
    what is already available on the machine (at least in first stages of
    development).

    Args:
        openpype_modules (_ModuleClass): Module object where modules are
            stored.
        modules_key (str): Key under which will be modules imported in
            `sys.modules`.
        log (logging.Logger): Logger object.

    Returns:
        List[str]: List of v3 addons to skip to load because v4 alternative is
            imported.
    """

    addons_to_skip_in_core = []

    bundle_info = _get_ayon_bundle_data()
    addons_info = _get_ayon_addons_information(bundle_info)
    if not addons_info:
        return addons_to_skip_in_core

    addons_dir = os.environ.get("AYON_ADDONS_DIR")
    if not addons_dir:
        addons_dir = os.path.join(
            appdirs.user_data_dir("AYON", "Ynput"),
            "addons"
        )

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
        if addon_name in ("openpype", "core"):
            continue

        dev_addon_info = dev_addons_info.get(addon_name, {})
        use_dev_path = dev_addon_info.get("enabled", False)

        addon_dir = None
        if use_dev_path:
            addon_dir = dev_addon_info["path"]
            if not addon_dir or not os.path.exists(addon_dir):
                log.warning((
                    "Dev addon {} {} path does not exists. Path \"{}\""
                ).format(addon_name, addon_version, addon_dir))
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
        imported_modules = []
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
                        imported_modules.append(mod)
                        break

            except BaseException:
                log.warning(
                    "Failed to import \"{}\"".format(basename),
                    exc_info=True
                )

        if not imported_modules:
            log.warning("Addon {} {} has no content to import".format(
                addon_name, addon_version
            ))
            continue

        if len(imported_modules) > 1:
            log.warning((
                "Skipping addon '{}'."
                " Multiple modules were found ({}) in dir {}."
            ).format(
                addon_name,
                ", ".join([m.__name__ for m in imported_modules]),
                addon_dir,
            ))
            continue

        mod = imported_modules[0]
        addon_alias = getattr(mod, "V3_ALIAS", None)
        if not addon_alias:
            addon_alias = addon_name
        addons_to_skip_in_core.append(addon_alias)
        new_import_str = "{}.{}".format(modules_key, addon_alias)

        sys.modules[new_import_str] = mod
        setattr(openpype_modules, addon_alias, mod)

    return addons_to_skip_in_core


def _load_ayon_core_addons_dir(
    ignore_addon_names, openpype_modules, modules_key, log
):
    addons_dir = os.path.join(AYON_CORE_ROOT, "addons")
    if not os.path.exists(addons_dir):
        return

    imported_modules = []

    # Make sure that addons which already have client code are not loaded
    #   from core again, with older code
    filtered_paths = []
    for name in os.listdir(addons_dir):
        if name in ignore_addon_names:
            continue
        path = os.path.join(addons_dir, name)
        if os.path.isdir(path):
            filtered_paths.append(path)

    for path in filtered_paths:
        while path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)

        for name in os.listdir(path):
            fullpath = os.path.join(path, name)
            if os.path.isfile(fullpath):
                basename, ext = os.path.splitext(name)
                if ext != ".py":
                    continue
            else:
                basename = name
            try:
                module = __import__(basename, fromlist=("",))
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, AYONAddon)
                    ):
                        new_import_str = "{}.{}".format(modules_key, basename)
                        sys.modules[new_import_str] = module
                        setattr(openpype_modules, basename, module)
                        imported_modules.append(module)
                        break

            except Exception:
                log.error(
                    "Failed to import addon '{}'.".format(fullpath),
                    exc_info=True
                )
    return imported_modules


def _load_addons_in_core(
    ignore_addon_names, openpype_modules, modules_key, log
):
    _load_ayon_core_addons_dir(
        ignore_addon_names, openpype_modules, modules_key, log
    )
    # Add current directory at first place
    #   - has small differences in import logic
    hosts_dir = os.path.join(AYON_CORE_ROOT, "hosts")
    modules_dir = os.path.join(AYON_CORE_ROOT, "modules")

    ignored_host_names = set(IGNORED_HOSTS_IN_AYON)
    ignored_module_dir_filenames = (
        set(IGNORED_DEFAULT_FILENAMES)
        | IGNORED_MODULES_IN_AYON
    )

    for dirpath in {hosts_dir, modules_dir}:
        if not os.path.exists(dirpath):
            log.warning((
                "Could not find path when loading AYON addons \"{}\""
            ).format(dirpath))
            continue

        is_in_modules_dir = dirpath == modules_dir
        if is_in_modules_dir:
            ignored_filenames = ignored_module_dir_filenames
        else:
            ignored_filenames = ignored_host_names

        for filename in os.listdir(dirpath):
            # Ignore filenames
            if filename in IGNORED_FILENAMES or filename in ignored_filenames:
                continue

            fullpath = os.path.join(dirpath, filename)
            basename, ext = os.path.splitext(filename)

            if basename in ignore_addon_names:
                continue

            # Validations
            if os.path.isdir(fullpath):
                # Check existence of init file
                init_path = os.path.join(fullpath, "__init__.py")
                if not os.path.exists(init_path):
                    log.debug((
                        "Addon directory does not contain __init__.py"
                        " file {}"
                    ).format(fullpath))
                    continue

            elif ext not in (".py", ):
                continue

            # TODO add more logic how to define if folder is addon or not
            # - check manifest and content of manifest
            try:
                # Don't import dynamically current directory modules
                new_import_str = "{}.{}".format(modules_key, basename)
                if is_in_modules_dir:
                    import_str = "ayon_core.modules.{}".format(basename)
                    default_module = __import__(import_str, fromlist=("", ))
                    sys.modules[new_import_str] = default_module
                    setattr(openpype_modules, basename, default_module)

                else:
                    import_str = "ayon_core.hosts.{}".format(basename)
                    # Until all hosts are converted to be able use them as
                    #   modules is this error check needed
                    try:
                        default_module = __import__(
                            import_str, fromlist=("", )
                        )
                        sys.modules[new_import_str] = default_module
                        setattr(openpype_modules, basename, default_module)

                    except Exception:
                        log.warning(
                            "Failed to import host folder {}".format(basename),
                            exc_info=True
                        )

            except Exception:
                if is_in_modules_dir:
                    msg = "Failed to import in-core addon '{}'.".format(
                        basename
                    )
                else:
                    msg = "Failed to import addon '{}'.".format(fullpath)
                log.error(msg, exc_info=True)


def _load_addons():
    # Support to use 'openpype' imports
    sys.modules["openpype"] = sys.modules["ayon_core"]

    # Key under which will be modules imported in `sys.modules`
    modules_key = "openpype_modules"

    # Change `sys.modules`
    sys.modules[modules_key] = openpype_modules = _ModuleClass(modules_key)

    log = Logger.get_logger("AddonsLoader")

    ignore_addon_names = _load_ayon_addons(
        openpype_modules, modules_key, log
    )
    _load_addons_in_core(
        ignore_addon_names, openpype_modules, modules_key, log
    )


_MARKING_ATTR = "_marking"
def mark_func(func):
    """Mark function to be used in report.

    Args:
        func (Callable): Function to mark.

    Returns:
        Callable: Marked function.
    """

    setattr(func, _MARKING_ATTR, True)
    return func


def is_func_marked(func):
    return getattr(func, _MARKING_ATTR, False)


@six.add_metaclass(ABCMeta)
class AYONAddon(object):
    """Base class of AYON addon.

    Attributes:
        id (UUID): Addon object id.
        enabled (bool): Is addon enabled.
        name (str): Addon name.

    Args:
        manager (AddonsManager): Manager object who discovered addon.
        settings (dict[str, Any]): AYON settings.
    """

    enabled = True
    _id = None

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

    def initialize(self, settings):
        """Initialization of addon attributes.

        It is not recommended to override __init__ that's why specific method
        was implemented.

        Args:
            settings (dict[str, Any]): Settings.
        """

        pass

    @mark_func
    def connect_with_addons(self, enabled_addons):
        """Connect with other enabled addons.

        Args:
            enabled_addons (list[AYONAddon]): Addons that are enabled.
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


class OpenPypeModule(AYONAddon):
    """Base class of OpenPype module.

    Deprecated:
        Use `AYONAddon` instead.

    Args:
        manager (AddonsManager): Manager object who discovered addon.
        settings (dict[str, Any]): Module settings (OpenPype settings).
    """

    # Disable by default
    enabled = False


class OpenPypeAddOn(OpenPypeModule):
    # Enable Addon by default
    enabled = True


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

        import openpype_modules

        self.log.debug("*** AYON addons initialization.")

        # Prepare settings for addons
        settings = self._settings
        if settings is None:
            settings = get_studio_settings()

        modules_settings = {}

        report = {}
        time_start = time.time()
        prev_start_time = time_start

        addon_classes = []
        for module in openpype_modules:
            # Go through globals in `ayon_core.modules`
            for name in dir(module):
                modules_item = getattr(module, name, None)
                # Filter globals that are not classes which inherit from
                #   AYONAddon
                if (
                    not inspect.isclass(modules_item)
                    or modules_item is AYONAddon
                    or modules_item is OpenPypeModule
                    or modules_item is OpenPypeAddOn
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

        aliased_names = []
        for addon_cls in addon_classes:
            name = addon_cls.__name__
            if issubclass(addon_cls, OpenPypeModule):
                # TODO change to warning
                self.log.debug((
                    "Addon '{}' is inherited from 'OpenPypeModule'."
                    " Please use 'AYONAddon'."
                ).format(name))

            try:
                # Try initialize module
                if issubclass(addon_cls, OpenPypeModule):
                    addon = addon_cls(self, modules_settings)
                else:
                    addon = addon_cls(self, settings)
                # Store initialized object
                self._addons.append(addon)
                self._addons_by_id[addon.id] = addon
                self._addons_by_name[addon.name] = addon
                # NOTE This will be removed with release 1.0.0 of ayon-core
                #   please use carefully.
                # Gives option to use alias name for addon for cases when
                #   name in OpenPype was not the same as in AYON.
                name_alias = getattr(addon, "openpype_alias", None)
                if name_alias:
                    aliased_names.append((name_alias, addon))
                enabled_str = "X"
                if not addon.enabled:
                    enabled_str = " "
                self.log.debug("[{}] {}".format(enabled_str, name))

                now = time.time()
                report[addon.__class__.__name__] = now - prev_start_time
                prev_start_time = now

            except Exception:
                self.log.warning(
                    "Initialization of addon '{}' failed.".format(name),
                    exc_info=True
                )

        for item in aliased_names:
            name_alias, addon = item
            if name_alias not in self._addons_by_name:
                self._addons_by_name[name_alias] = addon
                continue
            self.log.warning(
                "Alias name '{}' of addon '{}' is already assigned.".format(
                    name_alias, addon.name
                )
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
        enabled_modules = self.get_enabled_addons()
        self.log.debug("Has {} enabled modules.".format(len(enabled_modules)))
        for module in enabled_modules:
            try:
                if not is_func_marked(module.connect_with_addons):
                    module.connect_with_addons(enabled_modules)

                elif hasattr(module, "connect_with_modules"):
                    self.log.warning((
                        "DEPRECATION WARNING: Addon '{}' still uses"
                        " 'connect_with_modules' method. Please switch to use"
                        " 'connect_with_addons' method."
                    ).format(module.name))
                    module.connect_with_modules(enabled_modules)

            except Exception:
                self.log.error(
                    "BUG: Module failed on connection with other modules.",
                    exc_info=True
                )

            now = time.time()
            report[module.__class__.__name__] = now - prev_start_time
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
        cols = collections.OrderedDict()
        # Add addon names to first columnt
        cols["Addon name"] = list(sorted(
            addon.__class__.__name__
            for addon in self.addons
            if addon.__class__.__name__ in available_col_names
        ))
        # Add total key (as last addon)
        cols["Addon name"].append(self._report_total_key)

        # Add columns from report
        for label in self._report.keys():
            cols[label] = []

        total_addon_times = {}
        for addon_name in cols["Addon name"]:
            total_addon_times[addon_name] = 0

        for label, reported in self._report.items():
            for addon_name in cols["Addon name"]:
                col_time = reported.get(addon_name)
                if col_time is None:
                    cols[label].append("N/A")
                    continue
                cols[label].append("{:.3f}".format(col_time))
                total_addon_times[addon_name] += col_time

        # Add to also total column that should sum the row
        cols[self._report_total_key] = []
        for addon_name in cols["Addon name"]:
            cols[self._report_total_key].append(
                "{:.3f}".format(total_addon_times[addon_name])
            )

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

    # DEPRECATED - Module compatibility
    @property
    def modules(self):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated property"
            " 'modules' please use 'addons' instead."
        )
        return self.addons

    @property
    def modules_by_id(self):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated property"
            " 'modules_by_id' please use 'addons_by_id' instead."
        )
        return self.addons_by_id

    @property
    def modules_by_name(self):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated property"
            " 'modules_by_name' please use 'addons_by_name' instead."
        )
        return self.addons_by_name

    def get_enabled_module(self, *args, **kwargs):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated method"
            " 'get_enabled_module' please use 'get_enabled_addon' instead."
        )
        return self.get_enabled_addon(*args, **kwargs)

    def initialize_modules(self):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated method"
            " 'initialize_modules' please use 'initialize_addons' instead."
        )
        self.initialize_addons()

    def get_enabled_modules(self):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated method"
            " 'get_enabled_modules' please use 'get_enabled_addons' instead."
        )
        return self.get_enabled_addons()

    def get_host_module(self, host_name):
        self.log.warning(
            "DEPRECATION WARNING: Used deprecated method"
            " 'get_host_module' please use 'get_host_addon' instead."
        )
        return self.get_host_addon(host_name)


class TrayAddonsManager(AddonsManager):
    # Define order of addons in menu
    # TODO find better way how to define order
    addons_menu_order = (
        "user",
        "ftrack",
        "kitsu",
        "launcher_tool",
        "avalon",
        "clockify",
        "traypublish_tool",
        "log_viewer",
    )

    def __init__(self, settings=None):
        super(TrayAddonsManager, self).__init__(settings, initialize=False)

        self.tray_manager = None

        self.doubleclick_callbacks = {}
        self.doubleclick_callback = None

    def add_doubleclick_callback(self, addon, callback):
        """Register doubleclick callbacks on tray icon.

        Currently, there is no way how to determine which is launched. Name of
        callback can be defined with `doubleclick_callback` attribute.

        Missing feature how to define default callback.

        Args:
            addon (AYONAddon): Addon object.
            callback (FunctionType): Function callback.
        """

        callback_name = "_".join([addon.name, callback.__name__])
        if callback_name not in self.doubleclick_callbacks:
            self.doubleclick_callbacks[callback_name] = callback
            if self.doubleclick_callback is None:
                self.doubleclick_callback = callback_name
            return

        self.log.warning((
            "Callback with name \"{}\" is already registered."
        ).format(callback_name))

    def initialize(self, tray_manager, tray_menu):
        self.tray_manager = tray_manager
        self.initialize_addons()
        self.tray_init()
        self.connect_addons()
        self.tray_menu(tray_menu)

    def get_enabled_tray_addons(self):
        """Enabled tray addons.

        Returns:
            list[AYONAddon]: Enabled addons that inherit from tray interface.
        """

        return [
            addon
            for addon in self.get_enabled_addons()
            if isinstance(addon, ITrayAddon)
        ]

    def restart_tray(self):
        if self.tray_manager:
            self.tray_manager.restart()

    def tray_init(self):
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            try:
                addon._tray_manager = self.tray_manager
                addon.tray_init()
                addon.tray_initialized = True
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_init`.".format(
                        addon.name
                    ),
                    exc_info=True
                )

            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray init"] = report

    def tray_menu(self, tray_menu):
        ordered_addons = []
        enabled_by_name = {
            addon.name: addon
            for addon in self.get_enabled_tray_addons()
        }

        for name in self.addons_menu_order:
            addon_by_name = enabled_by_name.pop(name, None)
            if addon_by_name:
                ordered_addons.append(addon_by_name)
        ordered_addons.extend(enabled_by_name.values())

        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in ordered_addons:
            if not addon.tray_initialized:
                continue

            try:
                addon.tray_menu(tray_menu)
            except Exception:
                # Unset initialized mark
                addon.tray_initialized = False
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_menu`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray menu"] = report

    def start_addons(self):
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            if not addon.tray_initialized:
                if isinstance(addon, ITrayService):
                    addon.set_service_failed_icon()
                continue

            try:
                addon.tray_start()
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_start`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Addons start"] = report

    def on_exit(self):
        for addon in self.get_enabled_tray_addons():
            if addon.tray_initialized:
                try:
                    addon.tray_exit()
                except Exception:
                    self.log.warning(
                        "Addon \"{}\" crashed on `tray_exit`.".format(
                            addon.name
                        ),
                        exc_info=True
                    )

    # DEPRECATED
    def get_enabled_tray_modules(self):
        return self.get_enabled_tray_addons()

    def start_modules(self):
        self.start_addons()
