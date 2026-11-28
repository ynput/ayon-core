from __future__ import annotations

import collections
import os
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Optional

import ayon_api

from ayon_core.lib import (
    Logger,
    UserPreferences,
    UserPreferencesNotSupported,
)
from ayon_core.lib.icon_definitions import IconBase
from ayon_core.tools.launcher.abstract import (
    RecentActionItem,
    RECENT_ACTIONS_MAX,
)

if TYPE_CHECKING:
    from ayon_core.tools.launcher.abstract import AbstractLauncherBackend


# User preferences of the launcher and the item of the history in them
PREFERENCES_NAME = "io.ynput.core.launcher"
PREFERENCES_ITEM = "recent_actions"


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


class RecentActionsHistory:
    """Persistent store for recently triggered launcher actions.

    Keeps up to :data:`RECENT_ACTIONS_MAX` entries per user, in the
    ``recent_actions`` item of the ``io.ynput.core.launcher`` user
    preferences - so the history follows the user to any machine. AYON
    servers without the preferences API can't store it, nothing is
    recorded there, see 'is_supported'. Duplicate
    entries (same action in the same context) are deduplicated, the newest
    execution ends up on top. Favorited entries are pinned - they are listed
    first and newer actions never push them out.

    Everything needed to display an entry is stored with it, so showing the
    history costs a single request and needs no entity or action lookups.
    What is stored is a snapshot though - whether an action can still run is
    decided from its ids when it is triggered, not when it is displayed.

    Owned by 'ActionsModel', which records every action it triggered
    successfully. Recording happens off the thread that triggered the
    action.

    Args:
        controller (AbstractLauncherBackend): Controller used to get the
            entities of the context an action ran in.
        get_local_action_label_icon (Callable[[str], Optional[tuple]]):
            Current full label and icon of a local action by its
            identifier, 'None' if there is no such action.

    """

    log = Logger.get_logger("RecentActionsHistory")

    def __init__(
        self,
        controller: AbstractLauncherBackend,
        get_local_action_label_icon: Callable[[str], Optional[tuple]],
    ) -> None:
        self._controller = controller
        self._get_local_action_label_icon = get_local_action_label_icon
        # Thread safe, requests of the threads using it are serialized.
        self._preferences = UserPreferences(PREFERENCES_NAME)

        # Guards everything below. It is touched by the recording worker,
        # by the threads loading the history and by the main thread.
        self._lock = threading.Lock()
        self._items: Optional[list[RecentActionItem]] = None
        # Changes whenever the items are changed locally, so that a load
        # which was running meanwhile knows its result is outdated.
        self._revision = 0
        self._queued_items = collections.deque()
        self._save_requested = False
        self._saving = False
        self._worker: Optional[threading.Thread] = None
        # Whether the server can store the history, 'None' until the
        #   server answered a load of it
        self._supported: Optional[bool] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_loaded(self) -> bool:
        """Whether the history was loaded at least once."""
        return self._items is not None

    def is_supported(self) -> Optional[bool]:
        """Whether the server can store the history.

        Known once the server answered a load of the history, see
        'refresh'. Does not query anything.

        Returns:
            Optional[bool]: 'None' until the server answered.

        """
        return self._supported

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
        """Load the history from where it is stored.

        A single request, which also tells whether the server can store
        the history. Blocks, so it is meant to be called from a worker
        thread.
        """
        self._load()

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

    def _load(self) -> bool:
        """Load the stored history.

        Returns:
            bool: Whether it could be loaded.

        """
        with self._lock:
            revision = self._revision
            # What the server returns while a change is on its way to it
            # may or may not contain that change.
            is_storing = self._save_requested or self._saving

        items = self._fetch_items()
        if items is None:
            return False

        with self._lock:
            if not is_storing and revision == self._revision:
                self._items = items
        return True

    def _fetch_items(self) -> Optional[list[RecentActionItem]]:
        """Get the stored history, ready to be shown.

        Returns:
            Optional[list[RecentActionItem]]: Stored items, 'None' if they
                could not be loaded.

        """
        try:
            loaded = self._preferences.refresh()
        except UserPreferencesNotSupported:
            self._supported = False
            self.log.debug(
                "Recent actions were not loaded, the server can't store them."
            )
            return None

        # Storing replaces the whole history, so an empty history must not
        #   be used when it could not be received.
        if not loaded:
            self.log.warning("Failed to load recent actions.")
            return None
        self._supported = True

        raw = self._preferences.get_item(PREFERENCES_ITEM, default=None)
        if not isinstance(raw, list):
            raw = []

        items = []
        for entry in raw:
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
            label_icon = self._get_local_action_label_icon(item.identifier)
            if label_icon is None:
                continue
            label, icon = label_icon
            item.label = label
            item.icon = _icon_to_data(icon)

    def _store_items(self, items: list[RecentActionItem]) -> None:
        # Only the history item of the preferences is changed. Failures are
        #   logged by the preferences.
        self._preferences.set_item(
            PREFERENCES_ITEM, [item.to_data() for item in items]
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        action_type: str,
        identifier: str,
        addon_name: Optional[str],
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
        workfile_id: Optional[str],
        label: str,
        icon: Any,
    ) -> None:
        """Add a triggered action to the history.

        Recording costs a few requests. Doing that while the user launches
        something would make the launcher feel sluggish, so the context is
        resolved and the history stored in the background.

        Args:
            action_type (str): Type of action, 'local' or 'webaction'.
            identifier (str): Action identifier.
            addon_name (Optional[str]): Addon name (webactions only).
            project_name (Optional[str]): Project name.
            folder_id (Optional[str]): Folder id.
            task_id (Optional[str]): Task id.
            workfile_id (Optional[str]): Workfile id.
            label (str): Full label of the action.
            icon (Any): Icon definition of the action.

        """
        item = RecentActionItem(
            record_id=uuid.uuid4().hex,
            action_type=action_type,
            identifier=identifier,
            timestamp=time.time(),
            project_name=project_name,
            folder_id=folder_id,
            task_id=task_id,
            workfile_id=workfile_id,
            addon_name=addon_name,
            label=label or identifier,
            icon=_icon_to_data(icon),
        )
        with self._lock:
            self._queued_items.append(item)
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
                item = to_store = None
                if self._queued_items:
                    item = self._queued_items.popleft()
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

            if item is None:
                try:
                    self._store_items(to_store)
                finally:
                    with self._lock:
                        self._saving = False
                continue

            try:
                self._record(item)
            except Exception:
                self.log.error(
                    "Failed to record recent action '%s'.",
                    item.identifier,
                    exc_info=True,
                )

    def _record(self, item: RecentActionItem) -> None:
        # Storing replaces the whole history, so the stored one is loaded
        #   first, another machine may have changed it.
        if not self._load():
            self.log.debug(
                "Recent action '%s' was not recorded, the history could"
                " not be loaded.",
                item.identifier,
            )
            return

        # Snapshot how the context looks right now, so that displaying the
        # history later needs no lookups at all.
        self._fill_context_labels(item)

        with self._lock:
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

        Entities are served from what the launcher already has loaded
        whenever possible, folder and task types are those of the project.
        """
        project_name = item.project_name
        if not project_name:
            return

        project_entity = (
            self._controller.get_project_entity(project_name) or {}
        )
        item.project_code = project_entity.get("code")

        if item.folder_id:
            folder_entity = self._controller.get_folder_entity(
                project_name, item.folder_id
            )
            if folder_entity:
                item.folder_path = folder_entity["path"]
                folder_type = self._find_type(
                    project_entity.get("folderTypes"),
                    folder_entity.get("folderType"),
                )
                item.folder_icon = folder_type.get("icon")
                item.folder_color = folder_type.get("color")

        if not item.task_id:
            return

        task_entity = self._controller.get_task_entity(
            project_name, item.task_id
        )
        if task_entity:
            item.task_name = task_entity["name"]
            task_type = self._find_type(
                project_entity.get("taskTypes"),
                task_entity.get("taskType") or task_entity.get("type"),
            )
            item.task_icon = task_type.get("icon")
            item.task_color = task_type.get("color")

        if item.workfile_id:
            workfile_entity = ayon_api.get_workfile_info_by_id(
                project_name, item.workfile_id, fields={"path"}
            )
            if workfile_entity:
                item.workfile_name = os.path.basename(
                    workfile_entity["path"]
                )

    @staticmethod
    def _find_type(
        types: Optional[list[dict[str, Any]]], type_name: Optional[str]
    ) -> dict[str, Any]:
        """Folder or task type of the project by name, empty if unknown."""
        for type_data in types or []:
            if type_data["name"] == type_name:
                return type_data
        return {}
