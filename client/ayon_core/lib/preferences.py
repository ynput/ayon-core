"""Preferences of tools, of this machine or of the AYON user.

'LocalPreferences' are stored in a JSON file on this machine. They are
meant for what depends on the machine, e.g. sizes of windows.

'UserPreferences' follow the AYON user to every machine. They are stored
on AYON server with its preferences API, globally or per project. On
servers without that API they are stored on this machine instead.

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
    get_ayon_username,
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


class _ServerSupport:
    """Whether servers have the preferences API, by url of the server."""
    lock = threading.Lock()
    by_url: dict[str, bool] = {}


def _get_server_url() -> Optional[str]:
    try:
        return ayon_api.get_base_url()
    except Exception:
        return None


def _get_server_support() -> Optional[bool]:
    """Support of the current server, 'None' when not known yet."""
    server_url = _get_server_url()
    with _ServerSupport.lock:
        return _ServerSupport.by_url.get(server_url)


def _set_server_support(supported: bool) -> None:
    server_url = _get_server_url()
    if server_url is None:
        return
    with _ServerSupport.lock:
        _ServerSupport.by_url[server_url] = supported


class UserPreferences(ASettingRegistry):
    """Preferences of the AYON user, global or of a project.

    Stored on AYON server with its preferences API, so they follow the
    user to every machine. Items are the top-level fields of the
    preference. Only the user can read their preferences.

    Whether the server has the preferences API is checked with the first
    request. Servers without it store nothing, the preferences are stored
    on this machine instead, in 'tools/user_preferences/<username>' of
    the launcher local directory. They never mix with 'LocalPreferences'
    of the same name, nor with preferences of other AYON users.

    The preference is received on first use and cached, 'refresh'
    receives it again. Server requests block, a tool should not use the
    preferences in the main thread where that matters. Errors are logged,
    not raised: a failed read returns the default and a failed write
    keeps the value only in the cache.

    Example:
        >>> preferences = UserPreferences("io.ynput.core.launcher")
        >>> preferences.set_item("show_history", True)
        >>> preferences.get_item("show_history", default=False)
        True

    Args:
        key: Namespaced key of the preference, e.g.
            'io.ynput.core.launcher'.
        project_name: Project of the preference, global if not passed.

    Raises:
        ValueError: If the key is not valid.

    """
    log = Logger.get_logger("UserPreferences")

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
        self._local: Optional[_JSONPreferences] = None

    @property
    def key(self) -> str:
        """Key of the preference."""
        return self.name

    @property
    def project_name(self) -> Optional[str]:
        """Project of the preference, 'None' for global preference."""
        return self._project_name

    def is_stored_on_server(self) -> Optional[bool]:
        """Whether the preference is stored on AYON server.

        Returns:
            Optional[bool]: 'False' if the server has no preferences API
                and the preference is stored on this machine. 'None' if
                the server was not reachable yet.

        """
        with self._lock:
            self._ensure_loaded()
        return _get_server_support()

    def refresh(self) -> None:
        """Receive the preference again, e.g. changed on another machine.

        The cached items are kept if the server is not reachable.
        """
        with self._lock:
            self._loaded = True
            data = self._receive_data()
            if data is not None:
                self._data = data

    def get_data(self) -> dict[str, Any]:
        """All items of the preference.

        Returns:
            dict[str, Any]: Items by name.

        """
        with self._lock:
            self._ensure_loaded()
            return copy.deepcopy(self._data)

    def clear(self) -> None:
        """Delete the preference with all its items."""
        with self._lock:
            self._loaded = True
            self._data = {}
            supported = self._get_support()
            if supported is None:
                self._log_unreachable("deleted")
            elif not supported:
                local = self._get_local()
                if local is not None:
                    local.clear()
            else:
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
            supported = self._get_support()
            if supported is None:
                self._log_unreachable("stored")
            elif not supported:
                local = self._get_local()
                if local is not None:
                    local.set_item(name, value)
            else:
                # The server merges the item into the stored preference, so
                #   items changed meanwhile by other processes are kept.
                self._request("patch", payload={name: value})

    def _delete_item(self, name: str, ignore_missing: bool = True) -> None:
        with self._lock:
            self._ensure_loaded()
            if name not in self._data and not ignore_missing:
                raise RegistryItemNotFound(
                    f"Preference '{self.key}' doesn't contain '{name}'."
                )
            self._data.pop(name, None)
            supported = self._get_support()
            if supported is None:
                self._log_unreachable("deleted")
                return

            if not supported:
                local = self._get_local()
                if local is not None:
                    local.delete_item(name)
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

    def _get_support(self) -> Optional[bool]:
        """Support of the server, asks the server if not known yet.

        Expects '_lock' to be held.
        """
        supported = _get_server_support()
        if supported is None:
            # The server was not reachable before. What is received is
            #   used only to tell whether the server has the API.
            self._receive_data()
            supported = _get_server_support()
        return supported

    def _receive_data(self) -> Optional[dict[str, Any]]:
        """Receive the items of the preference.

        Returns:
            Optional[dict[str, Any]]: Items by name, 'None' if they could
                not be received.

        """
        if _get_server_support() is False:
            return self._get_local_data()

        # The list endpoint tells whether the server has the preferences
        #   API. A single preference could also be just not found.
        query = {"key_prefix": self.key}
        if self._project_name:
            query["project_name"] = self._project_name
        try:
            response = ayon_api.raw_get(f"preferences?{urlencode(query)}")
        except Exception:
            self.log.warning(
                "Failed to receive preference '%s'.", self.key, exc_info=True
            )
            return None

        if response.status_code in _NO_API_STATUS_CODES:
            _set_server_support(False)
            return self._get_local_data()

        if not response.ok:
            self._log_failed_request("receive", response)
            return None

        _set_server_support(True)
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

    def _get_local(self) -> Optional[_JSONPreferences]:
        """Storage on this machine, for servers without the API."""
        if self._local is None:
            try:
                username = get_ayon_username()
            except Exception:
                self.log.warning(
                    "Failed to get the AYON username for preference '%s'.",
                    self.key,
                    exc_info=True,
                )
                return None
            path_parts = ["tools", "user_preferences", username]
            if self._project_name:
                path_parts.extend(["projects", self._project_name])
            path_parts.append(f"{self.key}.json")
            self._local = _JSONPreferences(
                self.key, get_launcher_local_dir(*path_parts)
            )
        return self._local

    def _get_local_data(self) -> Optional[dict[str, Any]]:
        local = self._get_local()
        if local is None:
            return None
        return local.get_data()

    def _log_unreachable(self, action: str) -> None:
        self.log.warning(
            "Preference '%s' was not %s, the server is not reachable.",
            self.key,
            action,
        )

    def _log_failed_request(self, action: str, response: Any) -> None:
        self.log.warning(
            "Failed to %s preference '%s'. Server responded %s: %s",
            action,
            self.key,
            response.status_code,
            response.detail,
        )
