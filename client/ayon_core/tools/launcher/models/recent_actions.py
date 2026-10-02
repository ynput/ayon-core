from __future__ import annotations

import collections
import threading
import time
import uuid
from typing import TYPE_CHECKING, Optional

import ayon_api

from ayon_core.lib import (
    Logger,
    get_ayon_user_entity,
    get_ayon_username,
)
from ayon_core.lib.icon_definitions import IconBase
from ayon_core.tools.launcher.abstract import (
    RecentActionItem,
    RECENT_ACTIONS_MAX,
)

if TYPE_CHECKING:
    from ayon_core.tools.launcher.abstract import (
        AbstractLauncherBackend,
        AbstractLauncherFrontEnd,
    )


# Key in 'data.frontendPreferences' of the user. Preferences are the only
# part of user data a user without manager rights can change.
_PREFERENCES_KEY = "launcherRecentActions"
# The history was stored directly in user data at first, where the server
# ignores changes of users that are not managers. Still read from there so
# that those who could store it keep their history.
_LEGACY_USER_DATA_KEY = "recentActions"


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


def _action_key(item: RecentActionItem) -> tuple:
    """What makes two entries the same action in the same context."""
    return (
        item.action_type,
        item.identifier,
        item.addon_name,
        item.project_name,
        item.folder_id,
        item.task_id,
        item.workfile_id,
    )


class RecentActionsModel:
    """Persistent store for recently triggered launcher actions.

    Keeps up to :data:`RECENT_ACTIONS_MAX` entries per user, in
    ``data.frontendPreferences.launcherRecentActions`` of the user on AYON
    server - so the history follows the user to any machine. Duplicate
    entries (same action in the same context) are deduplicated, the newest
    execution ends up on top. Favorited entries are pinned - they are listed
    first and newer actions never push them out.

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
            context looked like. Names and types of the context entities
            are read through the same methods the UI uses, which are
            declared by 'AbstractLauncherFrontEnd'.

    """

    log = Logger.get_logger("RecentActionsModel")

    def __init__(
        self,
        controller: AbstractLauncherBackend | AbstractLauncherFrontEnd,
    ) -> None:
        self._controller = controller

        # Guards everything below. It is touched by the recording worker,
        # by the threads loading the history and by the main thread.
        self._lock = threading.Lock()
        self._items: Optional[list[RecentActionItem]] = None
        # Changes whenever the items are changed locally, so that a load
        # which was running meanwhile knows its result is outdated.
        self._revision = 0
        self._queued_triggers = collections.deque()
        self._save_requested = False
        self._saving = False
        self._worker: Optional[threading.Thread] = None
        self._prewarmed = False

        self._controller.register_event_callback(
            "action.trigger.finished",
            self._on_action_trigger_finished,
        )
        self._controller.register_event_callback(
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
        self._load(use_cached_user=False)

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

        # The launcher has just asked for the user while starting up, which
        # is recent enough to not ask the server again.
        threading.Thread(
            target=self._load,
            kwargs={"use_cached_user": True},
            name="recent-actions-prewarm",
            daemon=True,
        ).start()

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
            self._set_items(items)

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
            self._set_items(self._capped(self._items))

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

    def _set_items(self, items: list[RecentActionItem]) -> None:
        """Change the items locally and have them stored.

        Expects '_lock' to be held.
        """
        self._items = items
        self._revision += 1
        self._save_requested = True
        self._start_worker()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self, use_cached_user: bool) -> None:
        with self._lock:
            revision = self._revision
            # What the server returns while a change is on its way to it
            # may or may not contain that change.
            is_storing = self._save_requested or self._saving

        items = self._fetch_items(use_cached_user)
        if items is None:
            return

        with self._lock:
            if not is_storing and revision == self._revision:
                self._items = items

    def _fetch_items(
        self, use_cached_user: bool = False
    ) -> Optional[list[RecentActionItem]]:
        """Get the stored history, ready to be shown.

        Returns:
            Optional[list[RecentActionItem]]: Stored items, 'None' if they
                could not be loaded.

        """
        try:
            if use_cached_user:
                user = get_ayon_user_entity()
            else:
                user = ayon_api.get_user()
        except Exception:
            self.log.error(
                "Failed to load recent actions from AYON user.",
                exc_info=True,
            )
            return None

        user_data = user.get("data") or {}
        preferences = user_data.get("frontendPreferences") or {}
        raw = preferences.get(_PREFERENCES_KEY)
        if raw is None:
            raw = user_data.get(_LEGACY_USER_DATA_KEY)

        items = []
        for entry in raw or []:
            try:
                item = RecentActionItem.from_data(entry)
            except (TypeError, AttributeError):
                self.log.warning(
                    "Skipped invalid recent action: %s", entry, exc_info=True
                )
                continue
            # The row is unusable without something to call it.
            item.label = item.label or item.identifier
            items.append(item)

        self._update_local_actions(items)
        return items

    def _update_local_actions(self, items: list[RecentActionItem]) -> None:
        """Use current label and icon of local actions.

        The history is shared by all machines of the user, but the icon of
        a local action is usually a path to a file of an addon installed on
        the machine that recorded it. Local actions are known to this
        process, so how they look here can be read without any request.

        Webactions keep what is stored with them, their icons are urls and
        refreshing their labels would need a request per context.
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

    def _store_items(self, items: list[RecentActionItem]) -> None:
        try:
            # Only the passed key of the preferences is changed.
            response = ayon_api.raw_patch(
                f"users/{get_ayon_username()}/frontendPreferences",
                json={_PREFERENCES_KEY: [item.to_data() for item in items]},
            )
            response.raise_for_status()
        except Exception:
            self.log.error(
                "Failed to store recent actions to AYON user.",
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
                job = to_store = None
                if self._queued_triggers:
                    job = self._queued_triggers.popleft()
                elif self._save_requested:
                    # Changes made until now are stored by a single write.
                    self._save_requested = False
                    self._saving = True
                    to_store = list(self._items or [])
                else:
                    # Forget this thread while still holding the lock. The
                    # thread only finishes exiting after the lock is
                    # released - work queued in between would otherwise
                    # see it as still alive, start no new worker, and
                    # stay queued until some later event came along.
                    self._worker = None
                    return

            if job is None:
                try:
                    self._store_items(to_store)
                finally:
                    with self._lock:
                        self._saving = False
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

        self._fill_context_labels(item)

        # Storing replaces the whole history, so it has to be known first.
        loaded_items = None
        if not self.is_loaded():
            loaded_items = self._fetch_items()
            if loaded_items is None:
                self.log.warning(
                    "Recent action '%s' was not recorded, the history"
                    " could not be loaded.",
                    item.identifier,
                )
                return

        with self._lock:
            if self._items is None:
                self._items = loaded_items

            # Drop the same action executed on the same context, but carry
            # over whether it was favorited - re-running a favorite must
            # not quietly unpin it.
            key = _action_key(item)
            kept = []
            for existing in self._items:
                if _action_key(existing) == key:
                    item.favorite = item.favorite or existing.favorite
                    continue
                kept.append(existing)

            kept.insert(0, item)
            self._set_items(self._capped(kept))

    def _fill_context_labels(self, item: RecentActionItem) -> None:
        """Store names and type icons of the context with the item.

        Served from what the launcher already has loaded whenever possible.
        """
        project_name = item.project_name
        if not project_name:
            return

        project_entity = self._controller.get_project_entity(project_name)
        if project_entity:
            item.project_code = project_entity.get("code")

        if item.folder_id:
            folder_entity = self._controller.get_folder_entity(
                project_name, item.folder_id
            )
            if folder_entity:
                item.folder_path = folder_entity["path"]
                folder_type = self._find_type_item(
                    self._controller.get_folder_type_items(project_name),
                    folder_entity.get("folderType"),
                )
                if folder_type is not None:
                    item.folder_icon = folder_type.icon

        if not item.task_id:
            return

        task_entity = self._controller.get_task_entity(
            project_name, item.task_id
        )
        if task_entity:
            item.task_name = task_entity["name"]
            task_type = self._find_type_item(
                self._controller.get_task_type_items(project_name),
                task_entity.get("taskType") or task_entity.get("type"),
            )
            if task_type is not None:
                item.task_icon = task_type.icon
                item.task_color = task_type.color

        if item.workfile_id:
            for workfile_item in self._controller.get_workfile_items(
                project_name, item.task_id
            ):
                if workfile_item.workfile_id == item.workfile_id:
                    item.workfile_name = workfile_item.filename
                    break

    @staticmethod
    def _find_type_item(type_items, type_name):
        for type_item in type_items:
            if type_item.name == type_name:
                return type_item
        return None
