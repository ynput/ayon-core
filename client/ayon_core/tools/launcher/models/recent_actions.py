from __future__ import annotations

import time
import uuid
import dataclasses
from typing import TYPE_CHECKING

from ayon_core.lib import JSONSettingRegistry, get_ayon_username
from ayon_core.lib.local_settings import get_launcher_local_dir
from ayon_core.tools.launcher.abstract import (
    RecentActionItem,
    RECENT_ACTIONS_MAX,
)

if TYPE_CHECKING:
    from ayon_core.tools.launcher.abstract import AbstractLauncherBackend


_REGISTRY_KEY = "recent_actions"
_REGISTRY_NAME = "launcher_recent_actions"
_TRANSIENT_ITEM_FIELDS = {"icon", "task_name"}


class RecentActionsModel:
    """Persistent store for recently triggered launcher actions.

    Stores up to :data:`RECENT_ACTIONS_MAX` entries in a local JSON registry
    file so that the list survives launcher restarts.  Duplicate entries
    (same action + context) are automatically deduplicated – the newest
    execution always ends up at the top of the list.

    Subscribes to ``"action.trigger.finished"`` and
    ``"webaction.trigger.finished"`` controller events so that callers only
    need to trigger normal actions; recording happens automatically.

    Args:
        controller (AbstractLauncherBackend): Controller instance used for
            event subscription/emission and context resolution.
    """

    def __init__(self, controller: AbstractLauncherBackend) -> None:
        self._controller = controller
        self._registry: JSONSettingRegistry | None = None
        self._cache_by_key: dict[str, list[RecentActionItem]] = {}

        controller.register_event_callback(
            "action.trigger.finished",
            self._on_action_trigger_finished,
        )
        controller.register_event_callback(
            "webaction.trigger.finished",
            self._on_webaction_trigger_finished,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_recent_action_items(self) -> list[RecentActionItem]:
        """Return the recent action history (most recent first)."""
        return list(self._load())

    def get_recent_action_item(
        self, record_id: str
    ) -> RecentActionItem | None:
        """Return a single history entry by its *record_id*, or ``None``."""
        for item in self._load():
            if item.record_id == record_id:
                return item
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_current_username(self) -> str | None:
        try:
            return get_ayon_username()
        except Exception:
            return None

    def _get_registry_key(self) -> str:
        username = self._get_current_username()
        if not username:
            return _REGISTRY_KEY
        return f"{_REGISTRY_KEY}/{username}"

    def _get_registry(self) -> JSONSettingRegistry:
        if self._registry is None:
            self._registry = JSONSettingRegistry(
                _REGISTRY_NAME,
                get_launcher_local_dir(),
            )
        return self._registry

    def _load(self) -> list[RecentActionItem]:
        registry_key = self._get_registry_key()
        if registry_key in self._cache_by_key:
            return self._cache_by_key[registry_key]

        raw: list[dict] = self._get_registry().get_item(
            registry_key, default=None
        ) or []
        items: list[RecentActionItem] = []
        for entry in raw:
            try:
                entry = dict(entry)
                for key in _TRANSIENT_ITEM_FIELDS:
                    entry.pop(key, None)
                entry.setdefault("icon", None)
                entry.setdefault("task_name", None)
                items.append(RecentActionItem(**entry))
            except Exception:
                pass
        self._cache_by_key[registry_key] = items
        return items

    def _save(self, items: list[RecentActionItem]) -> None:
        registry_key = self._get_registry_key()
        self._cache_by_key[registry_key] = items
        raw = []
        for item in items:
            item_data = dataclasses.asdict(item)
            for key in _TRANSIENT_ITEM_FIELDS:
                item_data.pop(key, None)
            raw.append(item_data)
        self._get_registry().set_item(registry_key, raw)

    def _record(self, item: RecentActionItem) -> None:
        items = self._load()

        # Remove any existing duplicate (same action executed on same context)
        items = [
            existing for existing in items
            if not (
                existing.identifier == item.identifier
                and existing.action_type == item.action_type
                and existing.project_name == item.project_name
                and existing.folder_id == item.folder_id
                and existing.task_id == item.task_id
                and existing.workfile_id == item.workfile_id
            )
        ]

        items.insert(0, item)
        items = items[:RECENT_ACTIONS_MAX]

        self._save(items)
        self._controller.emit_event(
            "recent_actions.changed",
            {},
            "recent_actions.model",
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_action_trigger_finished(self, event: dict) -> None:
        if event.get("failed"):
            return

        record_id = uuid.uuid4().hex
        item = RecentActionItem(
            record_id=record_id,
            action_type="local",
            identifier=event["identifier"],
            label=event.get("full_label") or event["identifier"],
            icon=None,
            addon_name=None,
            addon_version=None,
            project_name=event.get("project_name"),
            folder_id=event.get("folder_id"),
            task_id=event.get("task_id"),
            task_name=None,
            workfile_id=event.get("workfile_id"),
            timestamp=time.time(),
        )
        self._record(item)

    def _on_webaction_trigger_finished(self, event: dict) -> None:
        if event.get("trigger_failed"):
            return
        if event.get("error_message"):
            return
        if not event.get("success", True):
            return

        record_id = uuid.uuid4().hex
        item = RecentActionItem(
            record_id=record_id,
            action_type="webaction",
            identifier=event["identifier"],
            label=event.get("full_label") or event["identifier"],
            icon=None,
            addon_name=event.get("addon_name"),
            addon_version=event.get("addon_version"),
            project_name=event.get("project_name"),
            folder_id=event.get("folder_id"),
            task_id=event.get("task_id"),
            task_name=None,
            workfile_id=event.get("workfile_id"),
            timestamp=time.time(),
        )
        self._record(item)
