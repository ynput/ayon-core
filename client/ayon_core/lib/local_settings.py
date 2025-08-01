# -*- coding: utf-8 -*-
"""Package to deal with saving and retrieving user specific settings."""
import os
import json
import platform
import configparser
import warnings
from datetime import datetime
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional, Any

import platformdirs
import ayon_api

_PLACEHOLDER = object()


# TODO should use 'KeyError' or 'Exception' as base
class RegistryItemNotFound(ValueError):
    """Raised when the item is not found in the keyring."""


class _Cache:
    username = None


def _get_ayon_appdirs(*args: str) -> str:
    return os.path.join(
        platformdirs.user_data_dir("AYON", "Ynput"),
        *args
    )


def get_ayon_appdirs(*args: str) -> str:
    """Local app data directory of AYON client.

    Deprecated:
        Use 'get_launcher_local_dir' or 'get_launcher_storage_dir' based on
            a use-case. Deprecation added 24/08/09 (0.4.4-dev.1).

    Args:
        *args (Iterable[str]): Subdirectories/files in the local app data dir.

    Returns:
        str: Path to directory/file in local app data dir.

    """
    warnings.warn(
        (
            "Function 'get_ayon_appdirs' is deprecated. Should be replaced"
            " with 'get_launcher_local_dir' or 'get_launcher_storage_dir'"
            " based on use-case."
        ),
        DeprecationWarning
    )
    return _get_ayon_appdirs(*args)


def get_launcher_storage_dir(*subdirs: str) -> str:
    """Get a storage directory for launcher.

    Storage directory is used for storing shims, addons, dependencies, etc.

    It is not recommended, but the location can be shared across
        multiple machines.

    Note:
        This function should be called at least once on bootstrap.

    Args:
        *subdirs (str): Subdirectories relative to storage dir.

    Returns:
        str: Path to storage directory.

    """
    storage_dir = os.getenv("AYON_LAUNCHER_STORAGE_DIR")
    if not storage_dir:
        storage_dir = _get_ayon_appdirs()

    return os.path.join(storage_dir, *subdirs)


def get_launcher_local_dir(*subdirs: str) -> str:
    """Get a local directory for launcher.

    Local directory is used for storing machine or user-specific data.

    The location is user-specific.

    Note:
        This function should be called at least once on the bootstrap.

    Args:
        *subdirs (str): Subdirectories relative to local dir.

    Returns:
        str: Path to local directory.

    """
    storage_dir = os.getenv("AYON_LAUNCHER_LOCAL_DIR")
    if not storage_dir:
        storage_dir = _get_ayon_appdirs()

    return os.path.join(storage_dir, *subdirs)


def get_addons_resources_dir(addon_name: str, *args) -> str:
    """Get a directory for storing resources for addons.

    Some addons might need to store ad-hoc resources that are not part of
        addon client package (e.g. because of size). Studio might define
        dedicated directory to store them with 'AYON_ADDONS_RESOURCES_DIR'
        environment variable. By default, is used 'addons_resources' in
        launcher storage (might be shared across platforms).

    Args:
        addon_name (str): Addon name.
        *args (str): Subfolders in the resources directory.

    Returns:
        str: Path to resources directory.

    """
    addons_resources_dir = os.getenv("AYON_ADDONS_RESOURCES_DIR")
    if not addons_resources_dir:
        addons_resources_dir = get_launcher_storage_dir("addons_resources")

    return os.path.join(addons_resources_dir, addon_name, *args)


class AYONSecureRegistry:
    """Store information using keyring.

    Registry should be used for private data that should be available only for
    user.

    All passed registry names will have added prefix `AYON/` to easier
    identify which data were created by AYON.

    Args:
        name(str): Name of registry used as the identifier for data.

    """
    def __init__(self, name: str) -> None:
        try:
            import keyring

        except Exception:
            raise NotImplementedError(
                "Python module `keyring` is not available."
            )

        # hack for cx_freeze and Windows keyring backend
        if platform.system().lower() == "windows":
            from keyring.backends import Windows

            keyring.set_keyring(Windows.WinVaultKeyring())

        # Force "AYON" prefix
        self._name = f"AYON/{name}"

    def set_item(self, name: str, value: str) -> None:
        """Set sensitive item into the system's keyring.

        This uses `Keyring module`_ to save sensitive stuff into the system's
        keyring.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        keyring.set_password(self._name, name, value)
        self.get_item.cache_clear()

    @lru_cache(maxsize=32)
    def get_item(
        self, name: str, default: Any = _PLACEHOLDER
    ) -> Optional[str]:
        """Get value of sensitive item from the system's keyring.

        See also `Keyring module`_

        Args:
            name (str): Name of the item.
            default (Any): Default value if the item is not available.

        Returns:
            value (str): Value of the item.

        Raises:
            RegistryItemNotFound: If the item doesn't exist and default
                is not defined.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        value = keyring.get_password(self._name, name)
        if value is not None:
            return value

        if default is not _PLACEHOLDER:
            return default

        raise RegistryItemNotFound(
            f"Item {self._name}:{name} not found in keyring."
        )

    def delete_item(self, name: str) -> None:
        """Delete value stored in the system's keyring.

        See also `Keyring module`_

        Args:
            name (str): Name of the item to be deleted.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        self.get_item.cache_clear()
        keyring.delete_password(self._name, name)


class ASettingRegistry(ABC):
    """Abstract class to defining structure of registry class.

    """
    def __init__(self, name: str) -> None:
        self._name = name

    @abstractmethod
    def _get_item(self, name: str) -> Any:
        """Get item value from registry."""

    @abstractmethod
    def _set_item(self, name: str, value: str) -> None:
        """Set item value to registry."""

    @abstractmethod
    def _delete_item(self, name: str) -> None:
        """Delete item from registry."""

    def __getitem__(self, name: str) -> Any:
        return self._get_item(name)

    def __setitem__(self, name: str, value: str) -> None:
        self._set_item(name, value)

    def __delitem__(self, name: str) -> None:
        self._delete_item(name)

    @property
    def name(self) -> str:
        return self._name

    def get_item(self, name: str) -> str:
        """Get item from settings registry.

        Args:
            name (str): Name of the item.

        Returns:
            value (str): Value of the item.

        Raises:
            RegistryItemNotFound: If the item doesn't exist.

        """
        return self._get_item(name)

    def set_item(self, name: str, value: str) -> None:
        """Set item to settings registry.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        """
        self._set_item(name, value)

    def delete_item(self, name: str) -> None:
        """Delete item from settings registry.

        Args:
            name (str): Name of the item.

        """
        self._delete_item(name)


class IniSettingRegistry(ASettingRegistry):
    """Class using :mod:`configparser`.

    This class is using :mod:`configparser` (ini) files to store items.

    """
    def __init__(self, name: str, path: str) -> None:
        super().__init__(name)
        # get registry file
        self._registry_file = os.path.join(path, f"{name}.ini")
        if not os.path.exists(self._registry_file):
            with open(self._registry_file, mode="w") as cfg:
                print("# Settings registry", cfg)
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                print(f"# {now}", cfg)

    def set_item_section(self, section: str, name: str, value: str) -> None:
        """Set item to specific section of ini registry.

        If section doesn't exists, it is created.

        Args:
            section (str): Name of section.
            name (str): Name of the item.
            value (str): Value of the item.

        """
        value = str(value)
        config = configparser.ConfigParser()

        config.read(self._registry_file)
        if not config.has_section(section):
            config.add_section(section)
        current = config[section]
        current[name] = value

        with open(self._registry_file, mode="w") as cfg:
            config.write(cfg)

    def _set_item(self, name: str, value: str) -> None:
        self.set_item_section("MAIN", name, value)

    def set_item(self, name: str, value: str) -> None:
        """Set item to settings ini file.

        This saves item to ``DEFAULT`` section of ini as each item there
        must reside in some section.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        """
        # this does the some, overridden just for different docstring.
        # we cast value to str as ini options values must be strings.
        super().set_item(name, str(value))

    def get_item(self, name: str) -> str:
        """Gets item from settings ini file.

        This gets settings from ``DEFAULT`` section of ini file as each item
        there must reside in some section.

        Args:
            name (str): Name of the item.

        Returns:
            str: Value of item.

        Raises:
            RegistryItemNotFound: If value doesn't exist.

        """
        return super().get_item(name)

    @lru_cache(maxsize=32)
    def get_item_from_section(self, section: str, name: str) -> str:
        """Get item from section of ini file.

        This will read ini file and try to get item value from specified
        section. If that section or item doesn't exist,
        :exc:`RegistryItemNotFound` is risen.

        Args:
            section (str): Name of ini section.
            name (str): Name of the item.

        Returns:
            str: Item value.

        Raises:
            RegistryItemNotFound: If value doesn't exist.

        """
        config = configparser.ConfigParser()
        config.read(self._registry_file)
        try:
            value = config[section][name]
        except KeyError:
            raise RegistryItemNotFound(
                f"Registry doesn't contain value {section}:{name}"
            )
        return value

    def _get_item(self, name: str) -> str:
        return self.get_item_from_section("MAIN", name)

    def delete_item_from_section(self, section: str, name: str) -> None:
        """Delete item from section in ini file.

        Args:
            section (str): Section name.
            name (str): Name of the item.

        Raises:
            RegistryItemNotFound: If the item doesn't exist.

        """
        self.get_item_from_section.cache_clear()
        config = configparser.ConfigParser()
        config.read(self._registry_file)
        try:
            _ = config[section][name]
        except KeyError:
            raise RegistryItemNotFound(
                f"Registry doesn't contain value {section}:{name}"
            )
        config.remove_option(section, name)

        # if section is empty, delete it
        if len(config[section].keys()) == 0:
            config.remove_section(section)

        with open(self._registry_file, mode="w") as cfg:
            config.write(cfg)

    def _delete_item(self, name):
        """Delete item from default section."""
        self.delete_item_from_section("MAIN", name)


class JSONSettingRegistry(ASettingRegistry):
    """Class using a json file as storage."""

    def __init__(self, name: str, path: str) -> None:
        super().__init__(name)
        self._registry_file = os.path.join(path, f"{name}.json")
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        header = {
            "__metadata__": {"generated": now},
            "registry": {}
        }

        # Use 'os.path.dirname' in case someone uses slashes in 'name'
        dirpath = os.path.dirname(self._registry_file)
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        if not os.path.exists(self._registry_file):
            with open(self._registry_file, mode="w") as cfg:
                json.dump(header, cfg, indent=4)

    @lru_cache(maxsize=32)
    def _get_item(self, name: str) -> str:
        """Get item value from the registry.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.get_item`

        """
        with open(self._registry_file, mode="r") as cfg:
            data = json.load(cfg)
            try:
                value = data["registry"][name]
            except KeyError:
                raise RegistryItemNotFound(
                    f"Registry doesn't contain value {name}"
                )
        return value

    def _set_item(self, name: str, value: str) -> None:
        """Set item value to the registry.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.set_item`

        """
        with open(self._registry_file, "r+") as cfg:
            data = json.load(cfg)
            data["registry"][name] = value
            cfg.truncate(0)
            cfg.seek(0)
            json.dump(data, cfg, indent=4)
        self._get_item.cache_clear()

    def _delete_item(self, name: str) -> None:
        with open(self._registry_file, "r+") as cfg:
            data = json.load(cfg)
            del data["registry"][name]
            cfg.truncate(0)
            cfg.seek(0)
            json.dump(data, cfg, indent=4)
        self._get_item.cache_clear()


class AYONSettingsRegistry(JSONSettingRegistry):
    """Class handling AYON general settings registry.

    Args:
        name (Optional[str]): Name of the registry. Using 'None' or not
            passing name is deprecated.

    """
    def __init__(self, name: Optional[str] = None) -> None:
        if not name:
            name = "AYON_settings"
            warnings.warn(
                (
                    "Used 'AYONSettingsRegistry' without 'name' argument."
                    " The argument will be required in future versions."
                ),
                DeprecationWarning,
                stacklevel=2,
            )
        path = get_launcher_storage_dir()
        super().__init__(name, path)


def get_local_site_id():
    """Get local site identifier.

    Identifier is created if does not exist yet.
    """
    # used for background syncing
    site_id = os.environ.get("AYON_SITE_ID")
    if site_id:
        return site_id

    site_id_path = get_launcher_local_dir("site_id")
    if os.path.exists(site_id_path):
        with open(site_id_path, "r") as stream:
            site_id = stream.read()

    if site_id:
        return site_id

    try:
        from ayon_common.utils import get_local_site_id as _get_local_site_id
        site_id = _get_local_site_id()
    except ImportError:
        raise ValueError("Couldn't access local site id")

    return site_id


def get_ayon_username():
    """AYON username used for templates and publishing.

    Uses current ayon api username.

    Returns:
        str: Username.

    """
    # Look for username in the connection stack
    # - this is used when service is working as other user
    #   (e.g. in background sync)
    # TODO @iLLiCiTiT - do not use private attribute of 'ServerAPI', rather
    #      use public method to get username from connection stack.
    con = ayon_api.get_server_api_connection()
    user_stack = getattr(con, "_as_user_stack", None)
    if user_stack is not None:
        username = user_stack.username
        if username is not None:
            return username

    # Cache the username to avoid multiple API calls
    # - it is not expected that user would change
    if _Cache.username is None:
        _Cache.username = ayon_api.get_user()["name"]
    return _Cache.username
