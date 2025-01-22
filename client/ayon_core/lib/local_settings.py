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

import appdirs
import ayon_api

_PLACEHOLDER = object()


def _get_ayon_appdirs(*args):
    return os.path.join(
        appdirs.user_data_dir("AYON", "Ynput"),
        *args
    )


def get_ayon_appdirs(*args):
    """Local app data directory of AYON client.

    Deprecated:
        Use 'get_launcher_local_dir' or 'get_launcher_storage_dir' based on
            use-case. Deprecation added 24/08/09 (0.4.4-dev.1).

    Args:
        *args (Iterable[str]): Subdirectories/files in local app data dir.

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
    """Get storage directory for launcher.

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
    """Get local directory for launcher.

    Local directory is used for storing machine or user specific data.

    The location is user specific.

    Note:
        This function should be called at least once on bootstrap.

    Args:
        *subdirs (str): Subdirectories relative to local dir.

    Returns:
        str: Path to local directory.

    """
    storage_dir = os.getenv("AYON_LAUNCHER_LOCAL_DIR")
    if not storage_dir:
        storage_dir = _get_ayon_appdirs()

    return os.path.join(storage_dir, *subdirs)


class AYONSecureRegistry:
    """Store information using keyring.

    Registry should be used for private data that should be available only for
    user.

    All passed registry names will have added prefix `AYON/` to easier
    identify which data were created by AYON.

    Args:
        name(str): Name of registry used as identifier for data.
    """
    def __init__(self, name):
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
        self._name = "/".join(("AYON", name))

    def set_item(self, name, value):
        # type: (str, str) -> None
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

    @lru_cache(maxsize=32)
    def get_item(self, name, default=_PLACEHOLDER):
        """Get value of sensitive item from system's keyring.

        See also `Keyring module`_

        Args:
            name (str): Name of the item.
            default (Any): Default value if item is not available.

        Returns:
            value (str): Value of the item.

        Raises:
            ValueError: If item doesn't exist and default is not defined.

        .. _Keyring module:
            https://github.com/jaraco/keyring

        """
        import keyring

        value = keyring.get_password(self._name, name)
        if value is not None:
            return value

        if default is not _PLACEHOLDER:
            return default

        # NOTE Should raise `KeyError`
        raise ValueError(
            "Item {}:{} does not exist in keyring.".format(self._name, name)
        )

    def delete_item(self, name):
        # type: (str) -> None
        """Delete value stored in system's keyring.

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
    """Abstract class defining structure of **SettingRegistry** class.

    It is implementing methods to store secure items into keyring, otherwise
    mechanism for storing common items must be implemented in abstract
    methods.

    Attributes:
        _name (str): Registry names.

    """

    def __init__(self, name):
        # type: (str) -> ASettingRegistry
        super(ASettingRegistry, self).__init__()

        self._name = name
        self._items = {}

    def set_item(self, name, value):
        # type: (str, str) -> None
        """Set item to settings registry.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        """
        self._set_item(name, value)

    @abstractmethod
    def _set_item(self, name, value):
        # type: (str, str) -> None
        # Implement it
        pass

    def __setitem__(self, name, value):
        self._items[name] = value
        self._set_item(name, value)

    def get_item(self, name):
        # type: (str) -> str
        """Get item from settings registry.

        Args:
            name (str): Name of the item.

        Returns:
            value (str): Value of the item.

        Raises:
            ValueError: If item doesn't exist.

        """
        return self._get_item(name)

    @abstractmethod
    def _get_item(self, name):
        # type: (str) -> str
        # Implement it
        pass

    def __getitem__(self, name):
        return self._get_item(name)

    def delete_item(self, name):
        # type: (str) -> None
        """Delete item from settings registry.

        Args:
            name (str): Name of the item.

        """
        self._delete_item(name)

    @abstractmethod
    def _delete_item(self, name):
        # type: (str) -> None
        """Delete item from settings."""
        pass

    def __delitem__(self, name):
        del self._items[name]
        self._delete_item(name)


class IniSettingRegistry(ASettingRegistry):
    """Class using :mod:`configparser`.

    This class is using :mod:`configparser` (ini) files to store items.

    """

    def __init__(self, name, path):
        # type: (str, str) -> IniSettingRegistry
        super(IniSettingRegistry, self).__init__(name)
        # get registry file
        self._registry_file = os.path.join(path, "{}.ini".format(name))
        if not os.path.exists(self._registry_file):
            with open(self._registry_file, mode="w") as cfg:
                print("# Settings registry", cfg)
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                print("# {}".format(now), cfg)

    def set_item_section(self, section, name, value):
        # type: (str, str, str) -> None
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

    def _set_item(self, name, value):
        # type: (str, str) -> None
        self.set_item_section("MAIN", name, value)

    def set_item(self, name, value):
        # type: (str, str) -> None
        """Set item to settings ini file.

        This saves item to ``DEFAULT`` section of ini as each item there
        must reside in some section.

        Args:
            name (str): Name of the item.
            value (str): Value of the item.

        """
        # this does the some, overridden just for different docstring.
        # we cast value to str as ini options values must be strings.
        super(IniSettingRegistry, self).set_item(name, str(value))

    def get_item(self, name):
        # type: (str) -> str
        """Gets item from settings ini file.

        This gets settings from ``DEFAULT`` section of ini file as each item
        there must reside in some section.

        Args:
            name (str): Name of the item.

        Returns:
            str: Value of item.

        Raises:
            ValueError: If value doesn't exist.

        """
        return super(IniSettingRegistry, self).get_item(name)

    @lru_cache(maxsize=32)
    def get_item_from_section(self, section, name):
        # type: (str, str) -> str
        """Get item from section of ini file.

        This will read ini file and try to get item value from specified
        section. If that section or item doesn't exist, :exc:`ValueError`
        is risen.

        Args:
            section (str): Name of ini section.
            name (str): Name of the item.

        Returns:
            str: Item value.

        Raises:
            ValueError: If value doesn't exist.

        """
        config = configparser.ConfigParser()
        config.read(self._registry_file)
        try:
            value = config[section][name]
        except KeyError:
            raise ValueError(
                "Registry doesn't contain value {}:{}".format(section, name))
        return value

    def _get_item(self, name):
        # type: (str) -> str
        return self.get_item_from_section("MAIN", name)

    def delete_item_from_section(self, section, name):
        # type: (str, str) -> None
        """Delete item from section in ini file.

        Args:
            section (str): Section name.
            name (str): Name of the item.

        Raises:
            ValueError: If item doesn't exist.

        """
        self.get_item_from_section.cache_clear()
        config = configparser.ConfigParser()
        config.read(self._registry_file)
        try:
            _ = config[section][name]
        except KeyError:
            raise ValueError(
                "Registry doesn't contain value {}:{}".format(section, name))
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
    """Class using json file as storage."""

    def __init__(self, name, path):
        # type: (str, str) -> JSONSettingRegistry
        super(JSONSettingRegistry, self).__init__(name)
        #: str: name of registry file
        self._registry_file = os.path.join(path, "{}.json".format(name))
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        header = {
            "__metadata__": {"generated": now},
            "registry": {}
        }

        if not os.path.exists(os.path.dirname(self._registry_file)):
            os.makedirs(os.path.dirname(self._registry_file), exist_ok=True)
        if not os.path.exists(self._registry_file):
            with open(self._registry_file, mode="w") as cfg:
                json.dump(header, cfg, indent=4)

    @lru_cache(maxsize=32)
    def _get_item(self, name):
        # type: (str) -> object
        """Get item value from registry json.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.get_item`

        """
        with open(self._registry_file, mode="r") as cfg:
            data = json.load(cfg)
            try:
                value = data["registry"][name]
            except KeyError:
                raise ValueError(
                    "Registry doesn't contain value {}".format(name))
        return value

    def get_item(self, name):
        # type: (str) -> object
        """Get item value from registry json.

        Args:
            name (str): Name of the item.

        Returns:
            value of the item

        Raises:
            ValueError: If item is not found in registry file.

        """
        return self._get_item(name)

    def _set_item(self, name, value):
        # type: (str, object) -> None
        """Set item value to registry json.

        Note:
            See :meth:`ayon_core.lib.JSONSettingRegistry.set_item`

        """
        with open(self._registry_file, "r+") as cfg:
            data = json.load(cfg)
            data["registry"][name] = value
            cfg.truncate(0)
            cfg.seek(0)
            json.dump(data, cfg, indent=4)

    def set_item(self, name, value):
        # type: (str, object) -> None
        """Set item and its value into json registry file.

        Args:
            name (str): name of the item.
            value (Any): value of the item.

        """
        self._set_item(name, value)

    def _delete_item(self, name):
        # type: (str) -> None
        self._get_item.cache_clear()
        with open(self._registry_file, "r+") as cfg:
            data = json.load(cfg)
            del data["registry"][name]
            cfg.truncate(0)
            cfg.seek(0)
            json.dump(data, cfg, indent=4)


class AYONSettingsRegistry(JSONSettingRegistry):
    """Class handling AYON general settings registry.

    Args:
        name (Optional[str]): Name of the registry.
    """

    def __init__(self, name=None):
        if not name:
            name = "AYON_settings"
        path = get_launcher_storage_dir()
        super(AYONSettingsRegistry, self).__init__(name, path)


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

    Uses curet ayon api username.

    Returns:
        str: Username.

    """
    return ayon_api.get_user()["name"]
