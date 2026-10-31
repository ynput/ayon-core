"""Preferences of tools, of this machine or of the AYON user.

'LocalPreferences' are stored in a JSON file on this machine. They are
meant for what depends on the machine, e.g. sizes of windows.

'UserPreferences' follow the AYON user to every machine. They are stored
on AYON server with its preferences API, globally or per project. Servers
without that API can't store them, 'UserPreferences.is_supported' tells
whether the current server can.

Both have 'get_item', 'set_item' and 'delete_item' of the setting
registries, so a tool can move from one to the other by changing the
class it uses.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

import ayon_api

from .log import Logger
from .local_settings import (
    _PLACEHOLDER,
    ASettingRegistry,
    RegistryItemNotFound,
    get_launcher_local_dir,
)

# Pattern of preference keys of AYON server. Used for both classes, so a
#   name is valid for either of them and is a valid file name.
_NAME_REGEX = re.compile(
    r"[a-zA-Z0-9_]([a-zA-Z0-9_.\-]{0,126}[a-zA-Z0-9_])?"
)
# Status codes of a server that does not have the preferences API
_NO_API_STATUS_CODES = {404, 405}
# Guards writes of all local preferences of this process, they are rare
_LOCAL_WRITE_LOCK = threading.Lock()


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_REGEX.fullmatch(name):
        raise ValueError(
            f"Invalid preferences name '{name}'. Use letters, digits,"
            " '_', '.' and '-', at most 128 characters, e.g."
            " 'io.ynput.core.launcher'."
        )


class _JSONPreferences(ASettingRegistry):
    """Items stored in a JSON file in the format of 'JSONSettingRegistry'.

    The file is read on each access, so changes of other processes are
    visible, and written only when an item changes. Errors of reading and
    writing are logged, not raised.

    Args:
        name: Name of the preferences.
        filepath: Path to the JSON file.

    """
    log = Logger.get_logger("LocalPreferences")

    def __init__(self, name: str, filepath: str) -> None:
        super().__init__(name)
        self._filepath = filepath

    @property
    def filepath(self) -> str:
        """Path to the JSON file, it may not exist yet."""
        return self._filepath

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
        """Delete all items."""
        with _LOCAL_WRITE_LOCK:
            try:
                os.remove(self._filepath)
            except FileNotFoundError:
                pass
            except OSError:
                self.log.warning(
                    "Failed to remove preferences file '%s'.",
                    self._filepath,
                    exc_info=True,
                )

    def _get_item(self, name: str, default: Any = _PLACEHOLDER) -> Any:
        data = self.get_data()
        if name in data:
            return data[name]
        if default is not _PLACEHOLDER:
            return default
        raise RegistryItemNotFound(
            f"Preferences '{self.name}' don't contain '{name}'."
        )

    def _set_item(self, name: str, value: Any) -> None:
        with _LOCAL_WRITE_LOCK:
            content = self._read_content()
            registry = content.get("registry")
            if not isinstance(registry, dict):
                registry = content["registry"] = {}
            registry[name] = value
            self._write_content(content)

    def _delete_item(self, name: str, ignore_missing: bool = True) -> None:
        with _LOCAL_WRITE_LOCK:
            content = self._read_content()
            registry = content.get("registry")
            if not isinstance(registry, dict) or name not in registry:
                if ignore_missing:
                    return
                raise RegistryItemNotFound(
                    f"Preferences '{self.name}' don't contain '{name}'."
                )
            registry.pop(name)
            self._write_content(content)

    def _read_content(self) -> dict[str, Any]:
        try:
            with open(self._filepath, "r", encoding="utf-8") as stream:
                content = json.load(stream)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.log.warning(
                "Failed to read preferences file '%s'.",
                self._filepath,
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

        dirpath = os.path.dirname(self._filepath)
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
            os.replace(tmp_path, self._filepath)
            tmp_path = None
        except (OSError, TypeError, ValueError):
            self.log.warning(
                "Failed to write preferences file '%s'.",
                self._filepath,
                exc_info=True,
            )
        finally:
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


class LocalPreferences(_JSONPreferences):
    """Preferences stored on this machine, of the user of the OS.

    Meant for what depends on the machine, e.g. sizes of windows. Use
    'UserPreferences' for what should follow the AYON user to other
    machines.

    Items are stored in '<name>.json' in the 'tools' folder of the
    launcher local directory, in the format of 'JSONSettingRegistry'. A
    'JSONSettingRegistry' with the same name in that folder is read as
    it is, e.g. 'LocalPreferences("launcher")' uses the registry the
    Launcher used before.

    Example:
        >>> preferences = LocalPreferences("io.ynput.core.my_tool")
        >>> preferences.set_item("splitter_sizes", [200, 400])
        >>> preferences.get_item("splitter_sizes", default=[])
        [200, 400]

    Args:
        name: Name of the preferences, namespaced like keys of
            'UserPreferences', e.g. 'io.ynput.core.my_tool'.

    Raises:
        ValueError: If the name is not valid.

    """
    def __init__(self, name: str) -> None:
        _validate_name(name)
        super().__init__(
            name, get_launcher_local_dir("tools", f"{name}.json")
        )


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

    if response.status_code in _NO_API_STATUS_CODES:
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
        _validate_name(key)
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
