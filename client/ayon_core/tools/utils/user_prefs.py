from __future__ import annotations

import json
import os
import sys
from typing import Any
import logging
from ayon_core.lib import Logger
from copy import deepcopy


class UserPreferences:
    """Singleton class to store and retrieve user preferences with
    JSON serialization."""

    _instance: UserPreferences | None = None
    _filepath: str
    _preferences: dict
    _last_saved_preferences: dict
    log: logging.Logger

    @classmethod
    def _get_default_filepath(cls) -> str:
        """Return an OS-appropriate path for storing user preferences."""
        if sys.platform == "win32":
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            return os.path.join(base, "AYON", "user_prefs.json")
        if sys.platform == "darwin":
            return os.path.join(
                os.path.expanduser("~"),
                "Library",
                "Application Support",
                "AYON",
                "user_prefs.json",
            )
        # Linux / other POSIX
        # honour XDG_CONFIG_HOME if defined and default to ~/.config
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
        return os.path.join(xdg, "AYON", "user_prefs.json")

    def __new__(cls, filepath: str | None = None):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._filepath = filepath or cls._get_default_filepath()
            instance._preferences = {}
            instance._last_saved_preferences = {}
            instance.log = Logger.get_logger(instance.__class__.__name__)
            instance._load()
            cls._instance = instance
        return cls._instance

    def _load(self) -> None:
        """Load preferences from JSON file."""
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r") as f:
                    self._preferences = json.load(f)
                self._last_saved_preferences = deepcopy(self._preferences)
            except (json.JSONDecodeError, IOError) as e:
                self.log.error(f"Failed to load user preferences: {e}")
                self._preferences = {}
            else:
                self.log.debug(f"Loaded user preferences from {self._filepath}")
        else:
            self.log.debug(f"No user preferences file found at {self._filepath}")

    def _save(self) -> None:
        """Save preferences to JSON file."""
        if self._preferences == self._last_saved_preferences:
            return  # No changes, skip saving
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        try:
            with open(self._filepath, "w") as f:
                json.dump(self._preferences, f, indent=2, sort_keys=True)
        except IOError as e:
            self.log.error(f"Failed to save user preferences: {e}")
        else:
            self._last_saved_preferences = deepcopy(self._preferences)
            self.log.debug(f"Saved user preferences to {self._filepath}")

    def _navigate_to_parent(
        self, parts: list[str], *, create_missing: bool = False
    ) -> dict | None:
        """Return parent dict for given key parts, or None if not found."""
        node = self._preferences
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                if not create_missing:
                    return None
                child = {}
                node[part] = child
            node = child
        return node

    def set(self, key: str, value: Any) -> None:
        """Set a preference value. Dot-separated keys address nested dicts."""
        parts = key.split(".")
        parent = self._navigate_to_parent(parts, create_missing=True)
        assert parent is not None
        parent[parts[-1]] = value
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a preference value. Dot-separated keys address nested dicts."""
        parts = key.split(".")
        parent = self._navigate_to_parent(parts)
        if parent is None or parts[-1] not in parent:
            return default
        return parent[parts[-1]]

    def remove(self, key: str) -> None:
        """Remove a preference. Dot-separated keys address nested dicts."""
        parts = key.split(".")
        parent = self._navigate_to_parent(parts)
        if parent is not None and parts[-1] in parent:
            del parent[parts[-1]]
            self._save()

    def clear(self) -> None:
        """Clear all preferences."""
        self._preferences.clear()
        self._save()

    def all(self) -> dict:
        """Get all preferences."""
        return self._preferences.copy()
