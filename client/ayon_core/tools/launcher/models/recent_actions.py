from __future__ import annotations

import dataclasses
import time
import uuid
from typing import TYPE_CHECKING

import ayon_api

from ayon_core.lib import Logger, get_ayon_username
from ayon_core.tools.launcher.abstract import (
    RecentActionRecord,
    RecentActionItem,
    RECENT_ACTIONS_MAX,
)

if TYPE_CHECKING:
    from ayon_core.tools.launcher.abstract import AbstractLauncherBackend


_USER_DATA_KEY = "recentActions"


class RecentActionsModel:
    """Persistent store for recently triggered launcher actions.

    Stores up to :data:`RECENT_ACTIONS_MAX` entries in current user's
    ``data.recentActions`` on AYON server. Duplicate entries (same action +
    context) are automatically deduplicated – the newest execution always
    ends up at the top of the list.

    Subscribes to ``"action.trigger.finished"`` and
    ``"webaction.trigger.finished"`` controller events so that callers only
    need to trigger normal actions; recording happens automatically.

    Args:
        controller (AbstractLauncherBackend): Controller instance used for
            event subscription/emission and context resolution.
    """

    log = Logger.get_logger("RecentActionsModel")

    def __init__(self, controller: AbstractLauncherBackend) -> None:
        self._controller = controller
        self._records_cache: list[RecentActionRecord] | None = None

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
        return [self._to_ui_item(record) for record in self._load()]

    def get_recent_action_record(
        self, record_id: str
    ) -> RecentActionRecord | None:
        """Return a single history entry by its *record_id*, or ``None``."""
        for record in self._load():
            if record.record_id == record_id:
                return record
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_ui_item(record: RecentActionRecord) -> RecentActionItem:
        return RecentActionItem(
            record_id=record.record_id,
            action_type=record.action_type,
            identifier=record.identifier,
            label=record.label,
            timestamp=record.timestamp,
            project_name=record.project_name,
            folder_id=record.folder_id,
            task_id=record.task_id,
            workfile_id=record.workfile_id,
            addon_name=record.addon_name,
            addon_version=record.addon_version,
            task_name=None,
            icon=None,
        )

    def _deserialize_items(self, raw: list[dict] | None) -> list[RecentActionRecord]:
        output: list[RecentActionRecord] = []
        for entry in raw or []:
            try:
                entry = dict(entry)
                entry.setdefault("addon_name", None)
                entry.setdefault("addon_version", None)
                entry.setdefault("project_name", None)
                entry.setdefault("folder_id", None)
                entry.setdefault("task_id", None)
                entry.setdefault("workfile_id", None)
                output.append(RecentActionRecord(**entry))
            except Exception:
                self.log.warning(
                    "Failed to deserialize recent action entry: %s",
                    entry,
                    exc_info=True,
                )
        return output

    @staticmethod
    def _serialize_items(items: list[RecentActionRecord]) -> list[dict]:
        raw: list[dict] = []
        for item in items:
            raw.append(dataclasses.asdict(item))
        return raw

    @staticmethod
    def _normalize_user_data(user_data: dict | None) -> dict:
        if not isinstance(user_data, dict):
            return {}

        normalized = dict(user_data)
        nested_data = normalized.pop("data", None)
        if isinstance(nested_data, dict):
            for key, value in nested_data.items():
                normalized.setdefault(key, value)
        return normalized

    def _load_from_user_data(self) -> list[RecentActionRecord]:
        user = ayon_api.get_user()
        user_data = self._normalize_user_data(user.get("data"))
        raw = user_data.get(_USER_DATA_KEY)
        if not isinstance(raw, list):
            return []
        return self._deserialize_items(raw)

    def _save_to_user_data(self, items: list[RecentActionRecord]) -> bool:
        username = get_ayon_username()

        try:
            user = ayon_api.get_user()
            user_data = self._normalize_user_data(user.get("data"))
            user_data[_USER_DATA_KEY] = self._serialize_items(items)
            response = ayon_api.raw_patch(
                f"users/{username}", json={"data": user_data}
            )
            response.raise_for_status()
            return True
        except Exception:
            self.log.warning("Failed to save recent actions to AYON user data.", exc_info=True)
            return False

    def _load(self) -> list[RecentActionRecord] | None:
        if self._records_cache is not None:
            return self._records_cache

        self._records_cache = self._load_from_user_data()
        return self._records_cache

    def _save(self, items: list[RecentActionRecord]) -> None:
        self._records_cache = list(items)
        if not self._save_to_user_data(items):
            self.log.warning(
                "Recent actions saved to in-memory cache only; "
                "server PATCH failed — history may be lost on restart."
            )

    def _record(self, item: RecentActionRecord) -> None:
        items = self._load() or []
        self.log.debug(
            "Recording recent action id=%r type=%r before_count=%d",
            item.identifier, item.action_type, len(items),
        )

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
        self.log.debug(
            "After dedup+cap count=%d max=%d", len(items), RECENT_ACTIONS_MAX
        )

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
        self.log.debug(
            "action.trigger.finished action_type='local' event=%r", event
        )
        if event.get("failed"):
            self.log.debug("action.trigger.finished skipped: failed=True")
            return

        record_id = uuid.uuid4().hex
        item = RecentActionRecord(
            record_id=record_id,
            action_type="local",
            identifier=event["identifier"],
            label=event.get("full_label") or event["identifier"],
            addon_name=None,
            addon_version=None,
            project_name=event.get("project_name"),
            folder_id=event.get("folder_id"),
            task_id=event.get("task_id"),
            workfile_id=event.get("workfile_id"),
            timestamp=time.time(),
        )
        self.log.debug(
            "action.trigger.finished recording action_type=%r record_id=%s identifier=%r",
            item.action_type, record_id, item.identifier,
        )
        self._record(item)

    def _on_webaction_trigger_finished(self, event: dict) -> None:
        self.log.debug(
            "webaction.trigger.finished action_type='webaction' event=%r", event
        )
        if event.get("trigger_failed"):
            self.log.debug("webaction.trigger.finished skipped: trigger_failed=True")
            return
        if event.get("error_message"):
            self.log.debug(
                "webaction.trigger.finished skipped: error_message=%r",
                event.get("error_message"),
            )
            return
        if not event.get("success", True):
            self.log.debug("webaction.trigger.finished skipped: success=False")
            return

        record_id = uuid.uuid4().hex
        item = RecentActionRecord(
            record_id=record_id,
            action_type="webaction",
            identifier=event["identifier"],
            label=event.get("full_label") or event["identifier"],
            addon_name=event.get("addon_name"),
            addon_version=event.get("addon_version"),
            project_name=event.get("project_name"),
            folder_id=event.get("folder_id"),
            task_id=event.get("task_id"),
            workfile_id=event.get("workfile_id"),
            timestamp=time.time(),
        )
        self.log.debug(
            "webaction.trigger.finished recording action_type=%r record_id=%s identifier=%r",
            item.action_type, record_id, item.identifier,
        )
        self._record(item)
