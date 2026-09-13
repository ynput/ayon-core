from __future__ import annotations

import collections
import dataclasses
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

import ayon_api

from ayon_core.lib import Logger
from ayon_core.lib.icon_definitions import IconBase
from ayon_core.tools.launcher.abstract import (
    RecentActionItem,
    RECENT_ACTIONS_MAX,
)

if TYPE_CHECKING:
    from ayon_core.tools.launcher.abstract import AbstractLauncherBackend


_USER_DATA_KEY = "recentActions"
# Fields that are persisted per item. Anything else found in stored data is
# ignored, so entries written by another version never break loading.
_ITEM_FIELDS = frozenset(
    field.name for field in dataclasses.fields(RecentActionItem)
)


def _icon_to_data(icon) -> Optional[dict]:
    """Icon definition in a form that survives a round trip to the server.

    'ActionItem.icon' is usually an 'IconBase' - both local actions and
    webactions end up with one. Those are dataclasses whose 'type' is a
    class attribute, so storing one field by field would quietly drop the
    very key that says how to read it back, leaving an entry that cannot
    be drawn anymore. 'to_data' keeps the whole definition of any icon
    type, in the shape 'get_icon_def_from_data' reads back.

    Args:
        icon (Union[IconBase, dict, None]): Icon definition of an action.

    Returns:
        Optional[dict]: Self describing icon definition, unchanged when it
            already is one.

    """
    if isinstance(icon, IconBase):
        return icon.to_data()
    if isinstance(icon, dict):
        return icon
    return None


class RecentActionsModel:
    """Persistent store for recently triggered launcher actions.

    Keeps up to :data:`RECENT_ACTIONS_MAX` entries in current user's
    ``data.recentActions`` on AYON server. Duplicate entries (same action in
    the same context) are deduplicated, the newest execution ends up on top.
    Favorited entries are pinned - they are listed first and newer actions
    never push them out.

    Everything needed to display an entry is stored with it, so showing the
    history costs a single request and needs no entity or action lookups.
    What is stored is a snapshot though - whether an action can still run is
    decided from its ids when it is triggered, not when it is displayed.

    Subscribes to ``"action.trigger.finished"`` and
    ``"webaction.trigger.finished"`` so that callers only need to trigger
    actions normally. Recording happens on its own, and off the thread that
    triggered the action.

    Args:
        controller (AbstractLauncherBackend): Controller used for event
            subscription and for resolving what a triggered action and its
            context looked like.

    """

    log = Logger.get_logger("RecentActionsModel")

    def __init__(self, controller: AbstractLauncherBackend) -> None:
        self._controller = controller

        # Guards '_items' and the recording queue. Both are touched by the
        # worker thread and by the thread loading the history.
        self._lock = threading.Lock()
        self._items: Optional[list[RecentActionItem]] = None
        self._queued_triggers = collections.deque()
        self._save_requested = False
        self._worker: Optional[threading.Thread] = None
        self._prewarmed = False

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

    def is_loaded(self) -> bool:
        """Whether the history was loaded at least once."""
        return self._items is not None

    def get_recent_action_items(self) -> list[RecentActionItem]:
        """Return the loaded history, favorites first.

        Both groups are ordered from most to least recently triggered. Does
        not query anything, the list is empty until 'refresh' ran.
        """
        with self._lock:
            if self._items is None:
                return []
            items = list(self._items)

        favorites = [item for item in items if item.favorite]
        return favorites + [item for item in items if not item.favorite]

    def get_recent_action_item(
        self, record_id: str
    ) -> Optional[RecentActionItem]:
        """Return a single loaded entry by its *record_id*, or ``None``."""
        for item in self.get_recent_action_items():
            if item.record_id == record_id:
                return item
        return None

    def refresh(self) -> None:
        """Load the history from the server.

        A single request. Blocks, so it is meant to be called from a worker
        thread.
        """
        items = self._load_from_user_data()
        self._relabel_local_actions(items)
        # An entry without a label cannot be presented in any useful way.
        # Relabeling just had its chance to give installed actions their
        # label back, so whatever is still nameless here is left over from
        # an older version - drop it for good.
        kept = [item for item in items if (item.label or "").strip()]
        dropped = len(items) - len(kept)
        with self._lock:
            # Changes still waiting to be written are newer than whatever
            # the server just returned, keep what we have in that case.
            if self._queued_triggers or self._save_requested:
                return
            self._items = kept
            if dropped:
                self.log.info(
                    "Removed %s recent action(s) without a label.", dropped
                )
                self._request_save()

    def prewarm(self) -> None:
        """Load the history in the background, once.

        Meant to be called when the launcher finished starting up, so that
        the history is already there the first time it is opened. Returns
        immediately and never loads more than once - every later open
        refreshes the history anyway.
        """
        with self._lock:
            if self._prewarmed:
                return
            self._prewarmed = True

        threading.Thread(
            target=self._prewarm_loop,
            name="recent-actions-prewarm",
            daemon=True,
        ).start()

    def _prewarm_loop(self) -> None:
        try:
            self.refresh()
        except Exception:
            self.log.warning(
                "Failed to pre-load recent actions.", exc_info=True
            )

    def _relabel_local_actions(
        self, items: list[RecentActionItem]
    ) -> None:
        """Update stored labels of local actions to their current ones.

        Local actions are known to this process, so how they are labelled
        right now can be read without contacting the server. Webactions
        keep the label stored with them, refreshing those would need a
        request per context and is not worth it - they are corrected the
        next time the action runs.
        """
        for item in items:
            if item.action_type != "local":
                continue
            label_icon = self._controller.get_local_action_label_icon(
                item.identifier
            )
            if label_icon is None:
                continue
            label, icon = label_icon
            item.label = label
            item.icon = _icon_to_data(icon)

    def remove_recent_action(self, record_id: str) -> None:
        """Drop an entry from the history and persist the change."""
        with self._lock:
            if self._items is None:
                return
            items = [
                item for item in self._items
                if item.record_id != record_id
            ]
            if len(items) == len(self._items):
                return
            self._items = items
            self._request_save()

    def set_favorite(self, record_id: str, favorite: bool) -> None:
        """Pin an entry to the top of the history, or unpin it."""
        with self._lock:
            if self._items is None:
                return
            for item in self._items:
                if item.record_id == record_id:
                    break
            else:
                return

            if item.favorite == favorite:
                return
            item.favorite = favorite
            # Unfavoriting may push the entry out of the capped part.
            self._items = self._capped(self._items)
            self._request_save()

    @staticmethod
    def _capped(
        items: list[RecentActionItem]
    ) -> list[RecentActionItem]:
        """Keep every favorite, and the newest of the rest.

        Args:
            items (list[RecentActionItem]): Items, most recent first.

        Returns:
            list[RecentActionItem]: Items that fit, order preserved.

        """
        output = []
        others = 0
        for item in items:
            if item.favorite:
                output.append(item)
            elif others < RECENT_ACTIONS_MAX:
                others += 1
                output.append(item)
        return output

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _deserialize_items(
        self, raw: Optional[list[Any]]
    ) -> list[RecentActionItem]:
        items: list[RecentActionItem] = []
        for entry in raw or []:
            if not isinstance(entry, dict):
                self.log.warning("Skipped invalid recent action: %s", entry)
                continue

            # Only known fields are used, entries written by a different
            # version may carry keys this one does not know about.
            kwargs = {
                key: value
                for key, value in entry.items()
                if key in _ITEM_FIELDS
            }
            try:
                items.append(RecentActionItem(**kwargs))
            except TypeError:
                self.log.warning(
                    "Skipped invalid recent action: %s", entry, exc_info=True
                )
        return items

    @staticmethod
    def _serialize_items(items: list[RecentActionItem]) -> list[dict]:
        return [dataclasses.asdict(item) for item in items]

    def _load_from_user_data(self) -> list[RecentActionItem]:
        try:
            user = ayon_api.get_user()
        except Exception:
            self.log.error(
                "Failed to load recent actions from AYON user data.",
                exc_info=True,
            )
            return []

        user_data = user.get("data")
        if not isinstance(user_data, dict):
            return []

        raw = user_data.get(_USER_DATA_KEY)
        if raw is None:
            # Entries stored under a nested 'data' key by older versions.
            nested = user_data.get("data")
            if isinstance(nested, dict):
                raw = nested.get(_USER_DATA_KEY)
        return self._deserialize_items(raw)

    def _save_to_user_data(self, items: list[RecentActionItem]) -> None:
        try:
            # Name and data come from the same response, so the history is
            # always written back to the user it was read from.
            user = ayon_api.get_user()
            user_data = user.get("data")
            user_data = dict(user_data) if isinstance(user_data, dict) else {}
            user_data[_USER_DATA_KEY] = self._serialize_items(items)
            response = ayon_api.raw_patch(
                f"users/{user['name']}", json={"data": user_data}
            )
            response.raise_for_status()
        except Exception:
            self.log.error(
                "Failed to save recent actions to AYON user data.",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _on_action_trigger_finished(self, event: dict) -> None:
        if event["failed"]:
            return
        self._queue_trigger("local", event)

    def _on_webaction_trigger_finished(self, event: dict) -> None:
        if (
            event["trigger_failed"]
            or event["error_message"]
            or not event["success"]
        ):
            return

        # A 'form' response only means the form was opened, the action
        # itself runs when the form is submitted - which triggers the
        # webaction again and records it then.
        if event["response_type"] == "form":
            return

        self._queue_trigger("webaction", event)

    def _queue_trigger(self, action_type: str, event: dict) -> None:
        """Hand a triggered action over to the recording worker.

        Recording costs a few requests. Doing that while the user launches
        something would make the launcher feel sluggish, so only the event
        data is taken here and all the work happens in the background.
        """
        with self._lock:
            self._queued_triggers.append((action_type, {
                "identifier": event["identifier"],
                "addon_name": event["addon_name"],
                "project_name": event["project_name"],
                "folder_id": event["folder_id"],
                "task_id": event["task_id"],
                "workfile_id": event["workfile_id"],
                "label": event["full_label"],
                "timestamp": time.time(),
            }))
            self._start_worker()

    def _request_save(self) -> None:
        """Persist the current items in the background.

        Expects '_lock' to be held. Repeated requests collapse into a
        single write.
        """
        self._save_requested = True
        self._start_worker()

    def _start_worker(self) -> None:
        """Start the recording worker. Expects '_lock' to be held."""
        if self._worker is not None and self._worker.is_alive():
            return
        # Daemon thread - a pending write is worth less than a launcher
        # that refuses to close.
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="recent-actions-recorder",
            daemon=True,
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if self._queued_triggers:
                    job = self._queued_triggers.popleft()
                    to_save = None
                elif self._save_requested:
                    self._save_requested = False
                    job = None
                    to_save = list(self._items or [])
                else:
                    return

            if job is None:
                self._save_to_user_data(to_save)
                continue

            action_type, data = job
            try:
                self._record(action_type, data)
            except Exception:
                self.log.error(
                    "Failed to record recent action '%s'.",
                    data["identifier"],
                    exc_info=True,
                )

    def _record(self, action_type: str, data: dict) -> None:
        item = RecentActionItem(
            record_id=uuid.uuid4().hex,
            action_type=action_type,
            identifier=data["identifier"],
            timestamp=data["timestamp"],
            project_name=data["project_name"],
            folder_id=data["folder_id"],
            task_id=data["task_id"],
            workfile_id=data["workfile_id"],
            addon_name=data["addon_name"],
            label=data["label"] or data["identifier"],
        )

        # Snapshot how the action and its context look right now, so that
        # displaying the history later needs no lookups at all.
        action_item = self._controller.get_action_item(
            item.action_type,
            item.identifier,
            item.addon_name,
            item.project_name,
            item.folder_id,
            item.task_id,
            item.workfile_id,
        )
        if action_item is not None:
            item.label = action_item.full_label
            item.icon = _icon_to_data(action_item.icon)

        labels = self._controller.get_context_labels(
            item.project_name,
            item.folder_id,
            item.task_id,
            item.workfile_id,
        )
        item.folder_path = labels.folder_path
        item.task_name = labels.task_name
        item.workfile_name = labels.workfile_name

        with self._lock:
            items = [] if self._items is None else list(self._items)
            # Drop the same action executed on the same context, but carry
            # over whether it was favorited - re-running a favorite must
            # not quietly unpin it.
            kept = []
            for existing in items:
                if (
                    existing.identifier == item.identifier
                    and existing.action_type == item.action_type
                    and existing.addon_name == item.addon_name
                    and existing.project_name == item.project_name
                    and existing.folder_id == item.folder_id
                    and existing.task_id == item.task_id
                    and existing.workfile_id == item.workfile_id
                ):
                    item.favorite = item.favorite or existing.favorite
                    continue
                kept.append(existing)

            kept.insert(0, item)
            self._items = self._capped(kept)
            to_save = list(self._items)

        self._save_to_user_data(to_save)
