"""Package to deal with saving and retrieving user specific settings.

Also preferences of tools, of this machine or of the AYON user.

'LocalPreferences' are stored in an SQLite database on this machine. They
are meant for what depends on the machine, e.g. sizes of windows.

'UserPreferences' follow the AYON user to every machine. They are stored
on AYON server with its preferences API, globally or per project. Servers
without that API can't store them, 'UserPreferences.is_supported' tells
whether the current server can.

Both have 'get_item', 'set_item' and 'delete_item' of the setting
registries, so a tool can move from one to the other by changing the
class it uses.
"""
from __future__ import annotations

import os
import re
import json
import logging
import platform
import tempfile
import threading
import configparser
import contextlib
import sqlite3
import warnings
import copy
from datetime import datetime
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Callable, Generator, Optional, Any
from urllib.parse import urlencode

import platformdirs
import ayon_api

from .cache import NestedCacheItem, CacheItem
from .log import Logger

_PLACEHOLDER = object()


# TODO should use 'KeyError' or 'Exception' as base
class RegistryItemNotFound(ValueError):
    """Raised when the item is not found in the keyring."""


class _Cache:
    username = None
    user_entities_by_name = NestedCacheItem()


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


class _FakeException(Exception):
    """Placeholder exception used if real exception is not available."""


class ASettingRegistry(ABC):
    """Abstract class defining structure of **SettingRegistry** class.

    Args:
        name(str): Name of registry used as the identifier for data.

    """
    def __init__(self, name: str) -> None:
        self._name = name

    @abstractmethod
    def _get_item(
        self, name: str, default: Any = _PLACEHOLDER
    ) -> Any:
        """Get item value from registry."""

    @abstractmethod
    def _set_item(self, name: str, value: Any) -> None:
        """Set item value to registry."""

    @abstractmethod
    def _delete_item(self, name: str, ignore_missing: bool) -> None:
        """Delete item from registry."""

    def __getitem__(self, name: str) -> Any:
        return self._get_item(name)

    def __setitem__(self, name: str, value: Any) -> None:
        self._set_item(name, value)

    def __delitem__(self, name: str) -> None:
        self._delete_item(name)

    @property
    def name(self) -> str:
        return self._name

    def get_item(
        self,
        name: str,
        default: Any = _PLACEHOLDER,
    ) -> Any:
        """Get item from settings registry.

        Args:
            name (str): Name of the item.
            default (Any): Default value if item is not available.

        Returns:
            Any: Value of the item.

        Raises:
            RegistryItemNotFound: If item doesn't exist.

        """
        return self._get_item(name, default)

    def set_item(self, name: str, value: Any) -> None:
        """Set item to settings registry.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        """
        self._set_item(name, value)

    def delete_item(self, name: str, ignore_missing: bool = True):
        """Delete item from settings registry.

        Args:
            name (str): Name of the item.
            ignore_missing (bool): If True, no error is raised if item doesn't
                exist.

        """
        self._delete_item(name, ignore_missing=ignore_missing)


class AYONSecureRegistry(ASettingRegistry):
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
        super().__init__(f"AYON/{name}")

    @lru_cache(maxsize=32)
    def _get_item(
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

        try:
            from keyring.errors import PasswordSetError
        except ImportError:
            PasswordSetError = _FakeException

        # Capture 'ItemNotFoundException' exception (on linux)
        try:
            from secretstorage.exceptions import ItemNotFoundException
        except ImportError:
            ItemNotFoundException = _FakeException

        value = None
        try:
            value = keyring.get_password(self._name, name)
        except (ItemNotFoundException, PasswordSetError):
            pass

        if value is not None:
            return value

        if default is not _PLACEHOLDER:
            return default

        raise RegistryItemNotFound(
            f"Item {self._name}:{name} not found in keyring."
        )

    def _set_item(self, name: str, value: str) -> None:
        """Set sensitive item into system's keyring.

        This uses `Keyring module`_ to save sensitive stuff into system's
        keyring.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        keyring.set_password(self._name, name, value)
        self._get_item.cache_clear()

    def _delete_item(self, name: str, ignore_missing: bool = True):
        """Delete value stored in system's keyring.

        See also `Keyring module`_

        Args:
            name (str): Name of the item to be deleted.
            ignore_missing (bool): If True, no error is raised if item doesn't
                exist.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        try:
            from keyring.errors import PasswordDeleteError
        except ImportError:
            PasswordDeleteError = _FakeException

        try:
            keyring.delete_password(self._name, name)
        except PasswordDeleteError:
            if not ignore_missing:
                raise RegistryItemNotFound(
                    f"Item {self._name}:{name} not found in keyring."
                )
        self._get_item.cache_clear()


class IniSettingRegistry(ASettingRegistry):
    """Class using :mod:`configparser`.

    This class is using :mod:`configparser` (ini) files to store items.

    """

    def __init__(self, name: str, path: str):
        super().__init__(name)
        # get registry file
        filepath = os.path.join(path, f"{name}.ini")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if not os.path.exists(filepath):
            with open(filepath, mode="w") as stream:
                print("# Settings registry", stream)
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                print(f"# {now}", stream)

        self._registry_file = filepath

    @property
    def filepath(self) -> str:
        return self._registry_file

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

        with open(self._registry_file, mode="w") as stream:
            config.write(stream)

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

    def get_item(self, name: str, default: Any = _PLACEHOLDER) -> str:
        """Gets item from settings ini file.

        This gets settings from ``DEFAULT`` section of ini file as each item
        there must reside in some section.

        Args:
            name (str): Name of the item.
            default (Any): Default value if item is not available.

        Returns:
            str: Value of item.

        Raises:
            RegistryItemNotFound: If value doesn't exist.

        """
        return super().get_item(name, default)

    @lru_cache(maxsize=32)
    def get_item_from_section(
        self, section: str, name: str, default: Any = _PLACEHOLDER
    ) -> Optional[str]:
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
            if default is not _PLACEHOLDER:
                return default
            raise RegistryItemNotFound(
                f"Registry doesn't contain value {section}:{name}"
            )
        return value

    def _get_item(
        self, name: str, default: Any = _PLACEHOLDER
    ) -> Any:
        return self.get_item_from_section("MAIN", name, default)

    def delete_item_from_section(
        self,
        section: str,
        name: str,
        ignore_missing: bool = True,
    ):
        """Delete item from section in ini file.

        Args:
            section (str): Section name.
            name (str): Name of the item.
            ignore_missing (bool): If True, no error is raised if item doesn't
                exist.

        Raises:
            RegistryItemNotFound: If the item doesn't exist.

        """
        self.get_item_from_section.cache_clear()
        config = configparser.ConfigParser()
        config.read(self._registry_file)
        try:
            _ = config[section][name]
        except KeyError:
            if ignore_missing:
                return
            raise RegistryItemNotFound(
                f"Registry doesn't contain value {section}:{name}"
            )
        config.remove_option(section, name)

        # if section is empty, delete it
        if len(config[section].keys()) == 0:
            config.remove_section(section)

        with open(self._registry_file, mode="w") as stream:
            config.write(stream)

    def _delete_item(self, name: str, ignore_missing: bool):
        """Delete item from default section."""
        self.delete_item_from_section("MAIN", name, ignore_missing)


class JSONSettingRegistry(ASettingRegistry):
    """Class using a json file as storage.

    The file is read on each access, so changes of other processes are
    visible, and written only when an item changes. Writes go through a
    temporary file, so a reader never gets half of the file. Errors of
    reading and writing are logged, not raised.

    Note:
        Writes are guarded only within this process. Two processes that
        change the same file at the same time may lose a change of one of
        them.

    Args:
        name (str): Name of the registry, also name of the file.
        path (str): Directory of the file.

    """
    # Guards writes of all JSON registries of this process, they are rare
    _write_lock = threading.Lock()

    def __init__(self, name: str, path: str) -> None:
        super().__init__(name)
        self._registry_file = os.path.join(path, f"{name}.json")

    @property
    def log(self) -> logging.Logger:
        return Logger.get_logger(self.__class__.__name__)

    @property
    def filepath(self) -> str:
        """Path to the JSON file, it may not exist yet."""
        return self._registry_file

    def get_data(self) -> dict[str, Any]:
        """All stored items.

        Returns:
            dict[str, Any]: Items by name.

        """
        registry = self._read_content().get("registry")
        if not isinstance(registry, dict):
            return {}
        return registry

    def clear(self) -> None:
        """Delete all items, by removing the file."""
        with self._write_lock:
            try:
                os.remove(self._registry_file)
            except FileNotFoundError:
                pass
            except OSError:
                self.log.warning(
                    "Failed to remove registry file '%s'.",
                    self._registry_file,
                    exc_info=True,
                )

    def _get_item(
        self, name: str, default: Any = _PLACEHOLDER
    ) -> Any:
        """Get item value from registry json.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.get_item`

        """
        data = self.get_data()
        if name in data:
            return data[name]
        if default is not _PLACEHOLDER:
            return default
        raise RegistryItemNotFound(
            f"Registry '{self.name}' doesn't contain value '{name}'."
        )

    def _set_item(self, name: str, value: Any) -> None:
        """Set item value to registry json.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.set_item`

        """
        with self._write_lock:
            content = self._read_content()
            registry = content.get("registry")
            if not isinstance(registry, dict):
                registry = content["registry"] = {}
            registry[name] = value
            self._write_content(content)

    def _delete_item(self, name: str, ignore_missing: bool = True) -> None:
        with self._write_lock:
            content = self._read_content()
            registry = content.get("registry")
            if not isinstance(registry, dict) or name not in registry:
                if ignore_missing:
                    return
                raise RegistryItemNotFound(
                    f"Registry '{self.name}' doesn't contain value '{name}'."
                )
            registry.pop(name)
            self._write_content(content)

    def _read_content(self) -> dict[str, Any]:
        try:
            with open(self._registry_file, "r", encoding="utf-8") as stream:
                content = json.load(stream)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.log.warning(
                "Failed to read registry file '%s'.",
                self._registry_file,
                exc_info=True,
            )
            return {}
        if not isinstance(content, dict):
            return {}
        return content

    def _write_content(self, content: dict[str, Any]) -> None:
        if "__metadata__" not in content:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            content["__metadata__"] = {"generated": now}

        dirpath = os.path.dirname(self._registry_file)
        tmp_path = None
        try:
            os.makedirs(dirpath, exist_ok=True)
            # Written to another file first, so a process reading the file
            #   meanwhile never gets half of it.
            fd, tmp_path = tempfile.mkstemp(
                prefix=f".{self.name}.", suffix=".tmp", dir=dirpath
            )
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(content, stream, indent=4)
            os.replace(tmp_path, self._registry_file)
            tmp_path = None
        except (OSError, TypeError, ValueError):
            self.log.warning(
                "Failed to write registry file '%s'.",
                self._registry_file,
                exc_info=True,
            )
        finally:
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


class AYONSettingsRegistry(JSONSettingRegistry):
    """Class handling AYON general settings registry.

    Args:
        name (Optional[str]): Name of the registry.
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
        path = get_launcher_local_dir()
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


def _get_ayon_service_username() -> Optional[str]:
    # TODO @iLLiCiTiT - do not use private attribute of 'ServerAPI', rather
    #      use public method to get username from connection stack.
    con = ayon_api.get_server_api_connection()
    user_stack = getattr(con, "_as_user_stack", None)
    if user_stack is None:
        return None
    return user_stack.username


def get_ayon_user_entity(username: Optional[str] = None) -> dict[str, Any]:
    """AYON user entity used for templates and publishing.

    Note:
        Usually only service and admin users can receive the full user entity.

    Args:
        username (Optional[str]): Username of the user. If not passed, then
            the current user in 'ayon_api' is used.

    Returns:
        dict[str, Any]: User entity.

    """
    service_username = _get_ayon_service_username()
    # Handle service user handling first
    if service_username:
        if username is None:
            username = service_username
        cache: CacheItem = _Cache.user_entities_by_name[username]
        if not cache.is_valid:
            if username == service_username:
                user = ayon_api.get_user()
            else:
                user = ayon_api.get_user(username)
            cache.update_data(user)
        return copy.deepcopy(cache.get_data())

    # Cache current user
    current_user = None
    if _Cache.username is None:
        current_user = ayon_api.get_user()
        _Cache.username = current_user["name"]

    if username is None:
        username = _Cache.username

    cache: CacheItem = _Cache.user_entities_by_name[username]
    if not cache.is_valid:
        user = None
        if username == _Cache.username:
            if current_user is None:
                current_user = ayon_api.get_user()
            user = current_user

        if user is None:
            user = ayon_api.get_user(username)
        cache.update_data(user)

    return copy.deepcopy(cache.get_data())


def get_ayon_username():
    """AYON username used for templates and publishing.

    Uses current ayon api username.

    Returns:
        str: Username.

    """
    user = get_ayon_user_entity()
    return user["name"]


# Pattern of preference keys of AYON server. Used for local and user
#   preferences, so a name is valid for both and is a valid file name.
_PREFERENCES_NAME_REGEX = re.compile(
    r"[a-zA-Z0-9_]([a-zA-Z0-9_.\-]{0,126}[a-zA-Z0-9_])?"
)
# Status codes of a server that does not have the preferences API
_NO_PREFERENCES_API_STATUS_CODES = {404, 405}


def _validate_preferences_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or not _PREFERENCES_NAME_REGEX.fullmatch(name)
    ):
        raise ValueError(
            f"Invalid preferences name '{name}'. Use letters, digits,"
            " '_', '.' and '-', at most 128 characters, e.g."
            " 'io.ynput.core.launcher'."
        )


# Tables of local preferences. Items are rows, so processes that change
#   different items at the same time don't overwrite each other.
_LOCAL_PREFERENCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS preferences (
    name  TEXT NOT NULL,
    item  TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (name, item)
);
CREATE TABLE IF NOT EXISTS imported_registries (
    name     TEXT NOT NULL,
    filepath TEXT NOT NULL,
    PRIMARY KEY (name, filepath)
);
"""


class LocalPreferences(ASettingRegistry):
    """Preferences stored on this machine, of the user of the OS.

    Meant for what depends on the machine, e.g. sizes of windows. Use
    'UserPreferences' for what should follow the AYON user to other
    machines.

    Items of all local preferences are stored in an SQLite database in
    the 'tools' folder of the launcher local directory, a row per item.
    Processes and threads can read and change them at the same time, a
    change of an item never loses changes of other items. Values are
    stored as JSON. Errors of the database are logged, not raised: a
    failed read returns the default and a failed write is lost.

    A database that SQLite reports as broken is moved aside to
    'preferences.db.broken-<time>' and a new one is created, so local
    preferences of all tools are reset instead of failing every time.

    The legacy registry, a 'JSONSettingRegistry' file tools used before,
    is imported once on first use. It is '<name>.json' in that folder if
    not passed, e.g. 'LocalPreferences("launcher")' has the items the
    Launcher stored before. Older versions of core keep using that file,
    changes are not written back to it.

    Example:
        >>> preferences = LocalPreferences("io.ynput.core.my_tool")
        >>> preferences.set_item("splitter_sizes", [200, 400])
        >>> preferences.get_item("splitter_sizes", default=[])
        [200, 400]

    Args:
        name: Name of the preferences, namespaced like keys of
            'UserPreferences', e.g. 'io.ynput.core.my_tool'.
        legacy_registry_filepath: Path to the 'JSONSettingRegistry' file
            the tool used before, to import on first use. Defaults to
            '<name>.json' in the 'tools' folder of the launcher local
            directory.

    Raises:
        ValueError: If the name is not valid.

    """
    log = Logger.get_logger("LocalPreferences")
    # Seconds to wait for another process that changes the database
    timeout = 10
    # Guards moving a broken database aside in this process
    _recover_lock = threading.Lock()

    def __init__(
        self, name: str, legacy_registry_filepath: Optional[str] = None
    ) -> None:
        _validate_preferences_name(name)
        super().__init__(name)
        if legacy_registry_filepath is None:
            legacy_registry_filepath = get_launcher_local_dir(
                "tools", f"{name}.json"
            )
        self._filepath = get_launcher_local_dir("tools", "preferences.db")
        self._legacy_registry_filepath = legacy_registry_filepath
        self._legacy_registry_imported = False

    @property
    def filepath(self) -> str:
        """Path to the database, shared by all local preferences."""
        return self._filepath

    @property
    def legacy_registry_filepath(self) -> str:
        """Path to the legacy registry imported on first use.

        It may not exist.
        """
        return self._legacy_registry_filepath

    def get_data(self) -> dict[str, Any]:
        """All stored items.

        Returns:
            dict[str, Any]: Items by name.

        """
        rows = self._query(
            "SELECT item, value FROM preferences WHERE name = ?",
            (self.name,),
        )
        data = {}
        for item, value in rows or []:
            try:
                data[item] = json.loads(value)
            except ValueError:
                self.log.warning(
                    "Failed to read item '%s' of preferences '%s'.",
                    item,
                    self.name,
                )
        return data

    def clear(self) -> None:
        """Delete all items."""
        self._change(
            "DELETE FROM preferences WHERE name = ?", (self.name,)
        )

    def import_registry(self, filepath: str) -> bool:
        """Import items of a 'JSONSettingRegistry' file.

        Each file is imported once, it is not imported again when the
        items are changed or deleted later. Items that are already set
        are kept.

        Args:
            filepath: Path to the JSON file of the registry.

        Returns:
            bool: Whether items were imported now.

        """
        if not os.path.isfile(filepath):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as stream:
                registry = json.load(stream).get("registry")
            if not isinstance(registry, dict):
                registry = {}
            rows = [
                (self.name, item, json.dumps(value))
                for item, value in registry.items()
            ]
        except (OSError, ValueError, TypeError, AttributeError):
            self.log.warning(
                "Failed to read registry file '%s'.", filepath, exc_info=True
            )
            return False

        source = os.path.normcase(os.path.abspath(filepath))

        def _import(connection: sqlite3.Connection) -> bool:
            # Locks the database, so the file is imported once also when
            #   processes import it at the same time.
            connection.execute("BEGIN IMMEDIATE")
            try:
                imported = connection.execute(
                    "SELECT 1 FROM imported_registries"
                    " WHERE name = ? AND filepath = ?",
                    (self.name, source),
                ).fetchone()
                if not imported:
                    connection.executemany(
                        "INSERT OR IGNORE INTO preferences"
                        " (name, item, value) VALUES (?, ?, ?)",
                        rows,
                    )
                    connection.execute(
                        "INSERT INTO imported_registries"
                        " (name, filepath) VALUES (?, ?)",
                        (self.name, source),
                    )
                connection.execute("COMMIT")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
                raise
            return not imported

        success, imported = self._run(
            _import, f"import registry file '{filepath}' to"
        )
        return success and imported

    def _get_item(self, name: str, default: Any = _PLACEHOLDER) -> Any:
        rows = self._query(
            "SELECT value FROM preferences WHERE name = ? AND item = ?",
            (self.name, name),
        )
        if rows:
            try:
                return json.loads(rows[0][0])
            except ValueError:
                self.log.warning(
                    "Failed to read item '%s' of preferences '%s'.",
                    name,
                    self.name,
                )
        if default is not _PLACEHOLDER:
            return default
        raise RegistryItemNotFound(
            f"Preferences '{self.name}' don't contain '{name}'."
        )

    def _set_item(self, name: str, value: Any) -> None:
        try:
            value = json.dumps(value)
        except (TypeError, ValueError):
            self.log.warning(
                "Failed to store item '%s' of preferences '%s'.",
                name,
                self.name,
                exc_info=True,
            )
            return
        self._change(
            "INSERT OR REPLACE INTO preferences (name, item, value)"
            " VALUES (?, ?, ?)",
            (self.name, name, value),
        )

    def _delete_item(self, name: str, ignore_missing: bool = True) -> None:
        deleted = self._change(
            "DELETE FROM preferences WHERE name = ? AND item = ?",
            (self.name, name),
        )
        if deleted == 0 and not ignore_missing:
            raise RegistryItemNotFound(
                f"Preferences '{self.name}' don't contain '{name}'."
            )

    def _query(
        self, sql: str, parameters: tuple[str, ...]
    ) -> Optional[list[tuple[str, ...]]]:
        """Read rows, 'None' if they could not be read."""
        self._ensure_legacy_registry_imported()
        # Nothing is created by reading
        if not os.path.exists(self._filepath):
            return []
        _, rows = self._run(
            lambda connection: connection.execute(sql, parameters).fetchall(),
            "read",
        )
        return rows

    def _change(self, sql: str, parameters: tuple[str, ...]) -> int:
        """Change rows, returns how many, '-1' if they were not changed."""
        self._ensure_legacy_registry_imported()
        success, count = self._run(
            lambda connection: connection.execute(sql, parameters).rowcount,
            "change",
        )
        return count if success else -1

    def _ensure_legacy_registry_imported(self) -> None:
        if not self._legacy_registry_imported:
            self._legacy_registry_imported = True
            self.import_registry(self._legacy_registry_filepath)

    def _run(
        self,
        function: Callable[[sqlite3.Connection], Any],
        action: str,
    ) -> tuple[bool, Any]:
        """Run a function with a connection, failures are logged.

        A broken database is moved aside and the function is run again
        with a new database.

        Args:
            function: Function that uses the connection.
            action: What the function does, for the log message.

        Returns:
            tuple[bool, Any]: Whether the function succeeded and what it
                returned.

        """
        for attempt in range(2):
            try:
                with self._connect() as connection:
                    return True, function(connection)
            except sqlite3.Error as exc:
                # Exactly 'DatabaseError' when the file is not a database
                #   or is malformed. Its subclasses are other errors, e.g.
                #   'OperationalError' of a locked database.
                if (
                    attempt == 0
                    and type(exc) is sqlite3.DatabaseError
                    and self._move_broken_database()
                ):
                    continue
                error = exc
            except OSError as exc:
                error = exc
            break

        self.log.warning(
            "Failed to %s preferences '%s'.",
            action,
            self.name,
            exc_info=error,
        )
        return False, None

    def _move_broken_database(self) -> bool:
        """Move a broken database aside, so a new one is created.

        Items of all local preferences are lost with it. The file is kept
        next to the database, e.g. for support.

        Returns:
            bool: Whether the database can be used again, also when it was
                moved meanwhile by another thread or process.

        """
        with self._recover_lock:
            # Another process may have replaced it since it failed
            if not self._is_database_broken():
                return True

            now = datetime.now().strftime("%Y%m%d-%H%M%S")
            broken_path = f"{self._filepath}.broken-{now}"
            # Journal first, it would be applied to the new database
            for suffix in ("-journal", "-wal", "-shm", ""):
                try:
                    os.replace(
                        f"{self._filepath}{suffix}",
                        f"{broken_path}{suffix}",
                    )
                except FileNotFoundError:
                    pass
                except OSError:
                    # E.g. opened by another process on Windows
                    self.log.warning(
                        "Failed to move broken preferences database '%s'.",
                        self._filepath,
                        exc_info=True,
                    )
                    return False

        self.log.warning(
            "Preferences database '%s' was broken, local preferences of"
            " all tools are reset. It was moved to '%s'.",
            self._filepath,
            broken_path,
        )
        return True

    def _is_database_broken(self) -> bool:
        """Whether the database exists and is broken."""
        if not os.path.exists(self._filepath):
            return False
        try:
            connection = sqlite3.connect(self._filepath, timeout=self.timeout)
            try:
                result = connection.execute("PRAGMA quick_check").fetchall()
            finally:
                connection.close()
        except sqlite3.OperationalError:
            # E.g. locked, that does not tell it is broken
            return False
        except sqlite3.DatabaseError:
            return True
        return result != [("ok",)]

    @contextlib.contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Connection to the database, closed on exit.

        Preferences are used rarely, so a connection is opened for each
        access. That also makes it safe to use from any thread. Every
        statement is committed on its own, unless a transaction is begun.
        """
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        connection = sqlite3.connect(
            self._filepath, timeout=self.timeout, isolation_level=None
        )
        try:
            connection.executescript(_LOCAL_PREFERENCES_SCHEMA)
            yield connection
        finally:
            connection.close()


class UserPreferencesNotSupported(RuntimeError):
    """AYON server has no preferences API to store user preferences."""


class _ServerSupport:
    """Whether servers have the preferences API, by url of the server."""
    lock = threading.Lock()
    # Held while a server is asked, so threads asking at the same time
    #   share one request.
    check_lock = threading.Lock()
    by_url: dict[str, bool] = {}


def _get_server_url() -> Optional[str]:
    try:
        return ayon_api.get_base_url()
    except Exception:
        return None


def _get_server_support() -> Optional[bool]:
    """Cached support of the current server, 'None' when not known."""
    server_url = _get_server_url()
    with _ServerSupport.lock:
        return _ServerSupport.by_url.get(server_url)


def _set_server_support(supported: bool) -> None:
    server_url = _get_server_url()
    if server_url is None:
        return
    with _ServerSupport.lock:
        _ServerSupport.by_url[server_url] = supported


def _list_preferences(query: dict[str, str]) -> Optional[Any]:
    """Ask the server for preferences of the current user.

    The list endpoint tells whether the server has the preferences API,
    a single preference could also be just not found. The support of the
    server is cached when the response tells it.

    Args:
        query: Query of the request, e.g. 'key_prefix'.

    Returns:
        Optional[Any]: Response of the server, 'None' if the request
            failed before the server responded.

    """
    try:
        response = ayon_api.raw_get(f"preferences?{urlencode(query)}")
    except Exception:
        UserPreferences.log.warning(
            "Failed to ask the server for user preferences.", exc_info=True
        )
        return None

    if response.status_code in _NO_PREFERENCES_API_STATUS_CODES:
        _set_server_support(False)
    elif response.ok:
        _set_server_support(True)
    return response


class UserPreferences(ASettingRegistry):
    """Preferences of the AYON user, global or of a project.

    Stored on AYON server with its preferences API, so they follow the
    user to every machine. Items are the top-level fields of the
    preference. Only the user can read their preferences.

    The preferences API is available since AYON server 1.17.3. On older
    servers every method that reads or changes the preference raises
    'UserPreferencesNotSupported', use 'is_supported' to check first.

    The preference is received on first use and cached, 'refresh'
    receives it again. Requests block, a tool should not use the
    preferences in the main thread where that matters. A server that is
    not reachable is logged, not raised: a failed read returns the
    default and a failed write keeps the value only in the cache.

    Example:
        >>> if UserPreferences.is_supported():
        ...     preferences = UserPreferences("io.ynput.core.launcher")
        ...     preferences.set_item("show_history", True)

    Args:
        key: Namespaced key of the preference, e.g.
            'io.ynput.core.launcher'.
        project_name: Project of the preference, global if not passed.

    Raises:
        ValueError: If the key is not valid.

    """
    log = Logger.get_logger("UserPreferences")
    # Oldest AYON server with the preferences API, for messages to the
    #   user. Whether a server has it is asked, not told by its version.
    min_server_version = "1.17.3"

    def __init__(
        self, key: str, project_name: Optional[str] = None
    ) -> None:
        _validate_preferences_name(key)
        super().__init__(key)
        self._project_name = project_name or None
        # Requests are done while holding the lock, so an item is never
        #   stored while an older value is on its way to the server.
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._loaded = False

    @staticmethod
    def is_supported() -> bool:
        """Whether the current AYON server can store user preferences.

        The server is asked once, the answer is cached for the url of the
        server. Asking blocks, call it in a thread where that matters.

        Returns:
            bool: Whether the server has the preferences API. 'False'
                also when the server could not be asked, that is not
                cached and the server is asked again on the next call.

        """
        supported = _get_server_support()
        if supported is not None:
            return supported

        with _ServerSupport.check_lock:
            supported = _get_server_support()
            if supported is None:
                # No preference has this key, so the response is empty
                _list_preferences(
                    {"key_prefix": "io.ynput.core.support_check"}
                )
                supported = _get_server_support()
        return bool(supported)

    @property
    def key(self) -> str:
        """Key of the preference."""
        return self.name

    @property
    def project_name(self) -> Optional[str]:
        """Project of the preference, 'None' for global preference."""
        return self._project_name

    def refresh(self) -> bool:
        """Receive the preference again, e.g. changed on another machine.

        The cached items are kept if the server is not reachable.

        Returns:
            bool: Whether the preference was received. A tool that
                replaces a whole item based on what it read should not
                do so when it was not, e.g. a list of entries.

        Raises:
            UserPreferencesNotSupported: If the server has no preferences
                API.

        """
        with self._lock:
            data = self._receive_data()
            self._loaded = True
            if data is None:
                return False
            self._data = data
            return True

    def get_data(self) -> dict[str, Any]:
        """All items of the preference.

        Returns:
            dict[str, Any]: Items by name.

        Raises:
            UserPreferencesNotSupported: If the server has no preferences
                API.

        """
        with self._lock:
            self._ensure_loaded()
            return copy.deepcopy(self._data)

    def clear(self) -> None:
        """Delete the preference with all its items.

        Raises:
            UserPreferencesNotSupported: If the server has no preferences
                API.

        """
        with self._lock:
            if not self._can_change("deleted"):
                return
            self._loaded = True
            self._data = {}
            # Not found means there is nothing to delete
            self._request("delete", ignore_codes={404})

    def _get_item(self, name: str, default: Any = _PLACEHOLDER) -> Any:
        with self._lock:
            self._ensure_loaded()
            if name in self._data:
                return copy.deepcopy(self._data[name])
        if default is not _PLACEHOLDER:
            return default
        raise RegistryItemNotFound(
            f"Preference '{self.key}' doesn't contain '{name}'."
        )

    def _set_item(self, name: str, value: Any) -> None:
        with self._lock:
            self._ensure_loaded()
            self._data[name] = copy.deepcopy(value)
            if self._can_change("stored"):
                # The server merges the item into the stored preference,
                #   so items changed meanwhile by other processes are kept.
                self._request("patch", payload={name: value})

    def _delete_item(self, name: str, ignore_missing: bool = True) -> None:
        with self._lock:
            self._ensure_loaded()
            if name not in self._data and not ignore_missing:
                raise RegistryItemNotFound(
                    f"Preference '{self.key}' doesn't contain '{name}'."
                )
            self._data.pop(name, None)
            if not self._can_change("deleted"):
                return

            # The server can't delete a single item, the preference is
            #   replaced with what is stored on the server without it. So
            #   items changed meanwhile by other processes are kept.
            data = self._receive_data()
            if data is None or name not in data:
                return
            data.pop(name)
            self._data = data
            self._request("put", payload=data)

    def _ensure_loaded(self) -> None:
        """Receive the preference on first use. Expects '_lock' held."""
        if not self._loaded:
            self.refresh()

    def _can_change(self, action: str) -> bool:
        """Whether the server can be asked to change the preference.

        Args:
            action: What would be done, for the log message.

        Returns:
            bool: 'False' if the server is not reachable, which is logged.

        Raises:
            UserPreferencesNotSupported: If the server has no preferences
                API.

        """
        if self.is_supported():
            return True
        self._raise_if_not_supported()
        self.log.warning(
            "Preference '%s' was not %s, the server is not reachable.",
            self.key,
            action,
        )
        return False

    def _raise_if_not_supported(self) -> None:
        if _get_server_support() is False:
            raise UserPreferencesNotSupported(
                f"AYON server '{_get_server_url()}' can't store user"
                " preferences, it requires AYON server"
                f" {self.min_server_version} or newer."
            )

    def _receive_data(self) -> Optional[dict[str, Any]]:
        """Receive the items of the preference.

        Returns:
            Optional[dict[str, Any]]: Items by name, 'None' if they could
                not be received.

        Raises:
            UserPreferencesNotSupported: If the server has no preferences
                API.

        """
        self._raise_if_not_supported()
        query = {"key_prefix": self.key}
        if self._project_name:
            query["project_name"] = self._project_name
        response = _list_preferences(query)
        self._raise_if_not_supported()
        if response is None:
            return None

        if not response.ok:
            self._log_failed_request("receive", response)
            return None

        for preference in response.data.get("preferences") or []:
            if preference.get("key") == self.key:
                data = preference.get("data")
                if isinstance(data, dict):
                    return data
        return {}

    def _request(
        self,
        method: str,
        payload: Optional[dict[str, Any]] = None,
        ignore_codes: Optional[set[int]] = None,
    ) -> None:
        """Change the preference on the server, failures are logged."""
        endpoint = f"preferences/{self.key}"
        if self._project_name:
            query = urlencode({"project_name": self._project_name})
            endpoint = f"{endpoint}?{query}"

        kwargs = {}
        if payload is not None:
            kwargs["json"] = payload
        function = getattr(ayon_api, f"raw_{method}")
        try:
            response = function(endpoint, **kwargs)
        except Exception:
            self.log.warning(
                "Failed to change preference '%s'.", self.key, exc_info=True
            )
            return
        if not response.ok and response.status_code not in (
            ignore_codes or set()
        ):
            self._log_failed_request("change", response)

    def _log_failed_request(self, action: str, response: Any) -> None:
        self.log.warning(
            "Failed to %s preference '%s'. Server responded %s: %s",
            action,
            self.key,
            response.status_code,
            response.detail,
        )
