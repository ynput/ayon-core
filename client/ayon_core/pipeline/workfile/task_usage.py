"""Task in-use tracking (advisory task locking).

A session that works on a task registers itself in the task entity data
on AYON server. Other users can then be notified that somebody is already
working on the task before they open a workfile of the task.

The information is advisory. It never blocks anybody from working on the
task and a task can be used by multiple sessions at the same time.

Each session is stored under its own key in the task data, the key is
'TASK_USAGE_KEY_PREFIX' followed by the session id. AYON server merges
top-level keys of entity data on update and removes keys with 'None' value,
so a session can add, update and remove itself with a single request
without reading the data first, and sessions can't override each other.

Sessions that did not update for longer than the stale timeout are ignored
and are removed when the task is claimed by a session, so sessions of
crashed applications do not stay on the task forever.
"""
from __future__ import annotations

import atexit
import datetime
import logging
import os
import socket
import time
from dataclasses import dataclass, asdict, fields, replace
from typing import Any, Optional

import ayon_api

from ayon_core.lib import (
    filter_profiles,
    get_ayon_username,
    get_local_site_id,
    is_headless_mode_enabled,
    is_in_tests,
)
from ayon_core.lib.events import register_event_callback
from ayon_core.settings import get_project_settings

log = logging.getLogger(__name__)

TASK_USAGE_KEY_PREFIX = "inUse_"
DEFAULT_STALE_TIMEOUT_HOURS = 8.0
# Do not update the task more often if nothing but the time did change.
#   Each update of a task creates an event on the server.
REFRESH_INTERVAL_SECONDS = 15 * 60

# Environment variables with value "1" in farm jobs
FARM_JOB_ENV_KEYS = (
    "AYON_RENDER_JOB",
    "AYON_PUBLISH_JOB",
    "AYON_REMOTE_PUBLISH",
)

# Environment variable with comma separated session ids the user did
#   confirm before the application was launched
ACKNOWLEDGED_SESSIONS_ENV_KEY = "AYON_TASK_IN_USE_ACKNOWLEDGED"

# Sessions of other users the user of current process was notified about
_acknowledged_session_ids: set[str] = set()


@dataclass
class TaskUsageSettings:
    """Task in-use settings for a context.

    Attributes:
        enabled (bool): Task in-use tracking is enabled for the context.
        stale_timeout_hours (float): Sessions without an update for more
            than this amount of hours are ignored.

    """
    enabled: bool = False
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS


@dataclass
class TaskUsageItem:
    """Session of a user working on a task.

    Attributes:
        session_id (str): Unique id of the process.
        username (str): AYON username.
        machine (str): Name of the machine.
        site_id (str): AYON site id of the machine.
        host_name (Optional[str]): Name of host integration, e.g. 'maya'.
        workfile (Optional[str]): Filename of the workfile opened in the
            session.
        opened_at (str): UTC time in ISO format when the session started
            to work on the task.
        updated_at (str): UTC time in ISO format of the last activity.

    """
    session_id: str
    username: str
    machine: str
    site_id: str
    host_name: Optional[str]
    workfile: Optional[str]
    opened_at: str
    updated_at: str

    @property
    def data_key(self) -> str:
        """Key under which is the session stored in task data."""
        return get_session_data_key(self.session_id)

    def to_data(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_data(cls, data: Any) -> Optional[TaskUsageItem]:
        """Create item from data stored on a task.

        Returns:
            Optional[TaskUsageItem]: Item or None if data are not valid.

        """
        if not isinstance(data, dict):
            return None
        try:
            item = cls(**{
                field.name: data.get(field.name)
                for field in fields(cls)
            })
        except TypeError:
            return None

        if (
            not item.session_id
            or not item.username
            or item.get_updated_at() is None
        ):
            return None
        return item

    def get_opened_at(self) -> Optional[datetime.datetime]:
        return _parse_time(self.opened_at)

    def get_updated_at(self) -> Optional[datetime.datetime]:
        return _parse_time(self.updated_at)


def get_session_data_key(session_id: str) -> str:
    """Key under which is a session stored in task data."""
    return f"{TASK_USAGE_KEY_PREFIX}{session_id}"


def _get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_time(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    try:
        output = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if output.tzinfo is None:
        output = output.replace(tzinfo=datetime.timezone.utc)
    return output


def _get_profiles(project_settings: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        project_settings
        ["core"]
        ["tools"]
        ["Workfiles"]
        .get("task_in_use_profiles")
    ) or []


def is_task_usage_enabled_in_project(
    project_name: str,
    project_settings: Optional[dict[str, Any]] = None,
) -> bool:
    """Task in-use tracking can be enabled for some context of a project.

    Can be used to skip queries of entities needed to find out if the
    tracking is enabled for specific context.

    Args:
        project_name (str): Project name.
        project_settings (Optional[dict[str, Any]]): Prepared project
            settings.

    Returns:
        bool: Project has at least one enabled profile.

    """
    if project_settings is None:
        project_settings = get_project_settings(project_name)
    return any(
        profile.get("enabled")
        for profile in _get_profiles(project_settings)
    )


def get_task_usage_settings(
    project_name: str,
    host_name: Optional[str],
    task_type: Optional[str],
    task_name: Optional[str],
    project_settings: Optional[dict[str, Any]] = None,
) -> TaskUsageSettings:
    """Task in-use settings for a context.

    Args:
        project_name (str): Project name.
        host_name (Optional[str]): Host name.
        task_type (Optional[str]): Task type.
        task_name (Optional[str]): Task name.
        project_settings (Optional[dict[str, Any]]): Prepared project
            settings.

    Returns:
        TaskUsageSettings: Settings for the context.

    """
    if project_settings is None:
        project_settings = get_project_settings(project_name)

    profiles = _get_profiles(project_settings)
    if not profiles:
        return TaskUsageSettings()

    profile = filter_profiles(
        profiles,
        {
            "host_names": host_name,
            "task_types": task_type,
            "task_names": task_name,
        },
        logger=log,
    )
    if not profile:
        return TaskUsageSettings()

    return TaskUsageSettings(
        enabled=profile["enabled"],
        stale_timeout_hours=profile.get(
            "stale_timeout_hours", DEFAULT_STALE_TIMEOUT_HOURS
        ),
    )


def parse_task_usage_items(
    task_data: Optional[dict[str, Any]]
) -> list[TaskUsageItem]:
    """Parse sessions stored in task data.

    Args:
        task_data (Optional[dict[str, Any]]): Value of task entity 'data'.

    Returns:
        list[TaskUsageItem]: All valid sessions stored on the task.

    """
    if not task_data:
        return []
    items = []
    for key, item_data in task_data.items():
        if not key.startswith(TASK_USAGE_KEY_PREFIX):
            continue
        item = TaskUsageItem.from_data(item_data)
        # Session must be stored under its own key
        if item is not None and item.data_key == key:
            items.append(item)
    return items


def filter_active_items(
    items: list[TaskUsageItem],
    stale_timeout_hours: float,
    now: Optional[datetime.datetime] = None,
) -> list[TaskUsageItem]:
    """Filter out sessions without recent activity.

    Args:
        items (list[TaskUsageItem]): Sessions to filter.
        stale_timeout_hours (float): Maximum hours since the last update.
        now (Optional[datetime.datetime]): Current time.

    Returns:
        list[TaskUsageItem]: Sessions that are not stale.

    """
    if now is None:
        now = _get_now()
    timeout = datetime.timedelta(hours=stale_timeout_hours)
    return [
        item
        for item in items
        if now - item.get_updated_at() <= timeout
    ]


def is_same_source(item: TaskUsageItem, other_item: TaskUsageItem) -> bool:
    """Sessions are of the same user in the same host on the same machine.

    A session with the same source as a session that just started is
    considered a leftover of a crashed application.
    """
    return (
        item.username == other_item.username
        and item.site_id == other_item.site_id
        and item.host_name == other_item.host_name
    )


def get_task_usage_cleanup_keys(
    task_data: Optional[dict[str, Any]],
    new_item: TaskUsageItem,
    stale_timeout_hours: float,
    now: Optional[datetime.datetime] = None,
) -> set[str]:
    """Keys of task data to remove when a session claims the task.

    Removed are stale and invalid sessions, and other sessions with the
    same source as the new session.

    Args:
        task_data (Optional[dict[str, Any]]): Value of task entity 'data'.
        new_item (TaskUsageItem): Session that claims the task.
        stale_timeout_hours (float): Maximum hours since the last update.
        now (Optional[datetime.datetime]): Current time.

    Returns:
        set[str]: Keys to remove from the task data.

    """
    all_keys = {
        key
        for key in (task_data or {})
        if key.startswith(TASK_USAGE_KEY_PREFIX)
    }
    keep_keys = {
        item.data_key
        for item in filter_active_items(
            parse_task_usage_items(task_data), stale_timeout_hours, now
        )
        if not is_same_source(item, new_item)
    }
    return all_keys - keep_keys - {new_item.data_key}


def filter_other_users_items(
    items: list[TaskUsageItem],
    username: str,
    acknowledged_session_ids: Optional[set[str]] = None,
) -> list[TaskUsageItem]:
    """Sessions the user should be notified about.

    Sessions of the user and sessions the user was already notified about
    are not returned.

    Args:
        items (list[TaskUsageItem]): Active sessions of a task.
        username (str): Current username.
        acknowledged_session_ids (Optional[set[str]]): Sessions the user
            was already notified about.

    Returns:
        list[TaskUsageItem]: Sessions of other users.

    """
    if acknowledged_session_ids is None:
        acknowledged_session_ids = set()
    return [
        item
        for item in items
        if (
            item.username != username
            and item.session_id not in acknowledged_session_ids
        )
    ]


def acknowledge_task_usage_items(items: list[TaskUsageItem]) -> None:
    """Mark sessions as known to the user of current process.

    The user is not notified about acknowledged sessions again.

    Args:
        items (list[TaskUsageItem]): Sessions the user was notified about.

    """
    _acknowledged_session_ids.update(item.session_id for item in items)


def get_task_usage_user_full_names(
    items: list[TaskUsageItem]
) -> dict[str, str]:
    """Get full names of users from sessions.

    Users without filled full name and users that are not accessible for
    current user are not in the output.

    Args:
        items (list[TaskUsageItem]): Sessions of users.

    Returns:
        dict[str, str]: Full name by username.

    """
    usernames = {item.username for item in items}
    if not usernames:
        return {}
    try:
        users = list(ayon_api.get_users(
            usernames=usernames, fields={"name", "attrib.fullName"}
        ))
    except Exception:
        log.debug("Failed to receive users information.", exc_info=True)
        return {}

    output = {}
    for user in users:
        full_name = (user.get("attrib") or {}).get("fullName")
        if full_name:
            output[user["name"]] = full_name
    return output


def _get_session_id() -> str:
    # Avoid circular import
    from ayon_core.pipeline.context_tools import get_process_id

    return get_process_id()


def get_task_usage_items(
    project_name: str,
    task_id: str,
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS,
) -> list[TaskUsageItem]:
    """Get active sessions working on a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        stale_timeout_hours (float): Maximum hours since the last update
            of a session.

    Returns:
        list[TaskUsageItem]: Active sessions of the task.

    """
    task_entity = ayon_api.get_task_by_id(
        project_name, task_id, fields={"id", "data"}
    )
    if not task_entity:
        return []
    return filter_active_items(
        parse_task_usage_items(task_entity.get("data")),
        stale_timeout_hours,
    )


def get_other_users_task_usage_items(
    project_name: str,
    task_id: str,
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS,
) -> list[TaskUsageItem]:
    """Get sessions of other users working on a task.

    Sessions acknowledged with 'acknowledge_task_usage_items' are skipped.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        stale_timeout_hours (float): Maximum hours since the last update
            of a session.

    Returns:
        list[TaskUsageItem]: Active sessions of other users.

    """
    return filter_other_users_items(
        get_task_usage_items(project_name, task_id, stale_timeout_hours),
        get_ayon_username(),
        _acknowledged_session_ids,
    )


def create_session_item(
    workfile: Optional[str] = None,
    host_name: Optional[str] = None,
) -> TaskUsageItem:
    """Create session item of current process.

    Args:
        workfile (Optional[str]): Filename of the opened workfile.
        host_name (Optional[str]): Name of host integration.

    Returns:
        TaskUsageItem: Session of current process.

    """
    now = _get_now().isoformat()
    return TaskUsageItem(
        session_id=_get_session_id(),
        username=get_ayon_username(),
        machine=socket.gethostname(),
        site_id=get_local_site_id(),
        host_name=host_name,
        workfile=workfile,
        opened_at=now,
        updated_at=now,
    )


def claim_task(
    project_name: str,
    task_id: str,
    item: TaskUsageItem,
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS,
) -> list[TaskUsageItem]:
    """Register a session as working on a task.

    Should be used when a session starts to work on a task. Stale sessions
    and leftovers of the same user are removed from the task. Use
    'update_task_session' for further updates of the session.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        item (TaskUsageItem): Session to register.
        stale_timeout_hours (float): Sessions without an update for more
            than this amount of hours are removed from the task.

    Returns:
        list[TaskUsageItem]: Other active sessions working on the task.

    """
    task_entity = ayon_api.get_task_by_id(
        project_name, task_id, fields={"id", "data"}
    )
    if not task_entity:
        return []

    task_data = task_entity.get("data") or {}
    cleanup_keys = get_task_usage_cleanup_keys(
        task_data, item, stale_timeout_hours
    )
    update_data: dict[str, Any] = {key: None for key in cleanup_keys}
    update_data[item.data_key] = item.to_data()
    ayon_api.update_task(project_name, task_id, data=update_data)

    return [
        other_item
        for other_item in filter_active_items(
            parse_task_usage_items(task_data), stale_timeout_hours
        )
        if (
            other_item.data_key not in cleanup_keys
            and other_item.session_id != item.session_id
        )
    ]


def update_task_session(
    project_name: str, task_id: str, item: TaskUsageItem
) -> None:
    """Update a session on a task.

    Only the key of the session is sent, the task data are not read.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        item (TaskUsageItem): Session to update.

    """
    ayon_api.update_task(
        project_name, task_id, data={item.data_key: item.to_data()}
    )


def release_task(
    project_name: str,
    task_id: str,
    session_id: Optional[str] = None,
) -> None:
    """Unregister a session from a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        session_id (Optional[str]): Session id. Session of current process
            is used if not passed.

    """
    if session_id is None:
        session_id = _get_session_id()
    ayon_api.update_task(
        project_name,
        task_id,
        data={get_session_data_key(session_id): None},
    )


@dataclass
class _TaskContext:
    project_name: str
    task_id: str
    settings: TaskUsageSettings


class TaskUsageTracker:
    """Keep current process registered on the task of current context.

    The tracker follows current context of the host integration. The task is
    claimed when context changes or a workfile is opened or saved, and is
    released when context changes to a different task or the process ends.

    When a task is claimed and other users are working on it, the user is
    notified about them, unless the user did already confirm them, e.g. in
    the Workfiles tool.

    Failures are only logged. The tracker must never break host callbacks.

    Args:
        host (AbstractHost): Host integration.

    """
    def __init__(self, host):
        self._host = host
        self._claimed: Optional[_TaskContext] = None
        self._item: Optional[TaskUsageItem] = None
        self._last_update: float = 0.0
        self._retry_after: float = 0.0
        self._context_cache: dict[tuple, Optional[_TaskContext]] = {}

    def sync(self) -> None:
        """Synchronize the task registration with current host context.

        Is not processed for some time after a failure, e.g. when server is
        not available or the user can't update tasks, to not slow down
        every save of a workfile.
        """
        if time.monotonic() < self._retry_after:
            return
        try:
            self._sync()
        except Exception:
            self._retry_after = time.monotonic() + REFRESH_INTERVAL_SECONDS
            log.warning("Failed to update task in-use data.", exc_info=True)

    def release(self) -> None:
        """Unregister from the claimed task."""
        claimed, self._claimed = self._claimed, None
        item, self._item = self._item, None
        if claimed is None or item is None:
            return
        try:
            release_task(
                claimed.project_name, claimed.task_id, item.session_id
            )
        except Exception:
            log.warning("Failed to release task in-use data.", exc_info=True)

    def _sync(self) -> None:
        context = self._get_task_context()

        claimed = self._claimed
        if claimed is not None and (
            context is None
            or context.project_name != claimed.project_name
            or context.task_id != claimed.task_id
        ):
            self.release()
            claimed = None

        if context is None:
            return

        workfile = self._get_workfile_name()
        now = time.monotonic()
        if claimed is None:
            self._claim(context, workfile)

        elif (
            workfile != self._item.workfile
            or now - self._last_update >= REFRESH_INTERVAL_SECONDS
        ):
            item = replace(
                self._item,
                workfile=workfile,
                updated_at=_get_now().isoformat(),
            )
            update_task_session(context.project_name, context.task_id, item)
            self._item = item

        else:
            return

        self._last_update = now

    def _claim(self, context: _TaskContext, workfile: Optional[str]) -> None:
        item = create_session_item(
            workfile, getattr(self._host, "name", None)
        )
        other_items = claim_task(
            context.project_name,
            context.task_id,
            item,
            context.settings.stale_timeout_hours,
        )
        self._claimed = context
        self._item = item

        other_items = filter_other_users_items(
            other_items, item.username, _acknowledged_session_ids
        )
        # Sessions stay unconfirmed if the user could not be notified, the
        #   user is asked about them when opens a workfile of the task
        if other_items and self._notify(other_items):
            acknowledge_task_usage_items(other_items)

    def _notify(self, items: list[TaskUsageItem]) -> bool:
        """Notify user that other users are working on the claimed task.

        The task is already in use by current process at this point, e.g.
        the application was launched with a workfile, so the user can only
        be informed.

        Returns:
            bool: The notice will be shown to the user.

        """
        log.warning(
            "Task is in use by other users: %s",
            ", ".join(sorted({item.username for item in items})),
        )
        try:
            from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (
                show_task_in_use_notice,
            )

            return show_task_in_use_notice(
                items, get_task_usage_user_full_names(items)
            )
        except Exception:
            log.debug(
                "Failed to show task in-use notice.", exc_info=True
            )
        return False

    def _get_workfile_name(self) -> Optional[str]:
        get_current_workfile = getattr(
            self._host, "get_current_workfile", None
        )
        if get_current_workfile is None:
            return None
        filepath = get_current_workfile()
        if not filepath:
            return None
        return os.path.basename(filepath)

    def _get_task_context(self) -> Optional[_TaskContext]:
        """Task of current host context with enabled in-use tracking."""
        context = self._host.get_current_context()
        project_name = context.get("project_name")
        folder_path = context.get("folder_path")
        task_name = context.get("task_name")
        if not project_name or not folder_path or not task_name:
            return None

        cache_key = (project_name, folder_path, task_name)
        if cache_key not in self._context_cache:
            self._context_cache[cache_key] = self._query_task_context(
                project_name, folder_path, task_name
            )
        return self._context_cache[cache_key]

    def _query_task_context(
        self, project_name: str, folder_path: str, task_name: str
    ) -> Optional[_TaskContext]:
        # Avoid queries of entities if the tracking is not used in project
        if not is_task_usage_enabled_in_project(project_name):
            return None

        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path, fields={"id"}
        )
        if not folder_entity:
            return None
        task_entity = ayon_api.get_task_by_name(
            project_name,
            folder_entity["id"],
            task_name,
            fields={"id", "name", "taskType"},
        )
        if not task_entity:
            return None

        settings = get_task_usage_settings(
            project_name,
            getattr(self._host, "name", None),
            task_entity["taskType"],
            task_entity["name"],
        )
        if not settings.enabled:
            return None
        return _TaskContext(project_name, task_entity["id"], settings)


# Keep the tracker referenced, event callbacks are stored as weak references
_tracker: Optional[TaskUsageTracker] = None


def _on_exit() -> None:
    if _tracker is not None:
        _tracker.release()


def _connect_qt_quit() -> None:
    """Release the task when Qt application is about to quit.

    Not all applications do trigger 'atexit' callbacks on exit.
    """
    try:
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_on_exit)
    except Exception:
        log.debug("Failed to connect to Qt application quit.", exc_info=True)


def install_task_usage_tracker(host) -> Optional[TaskUsageTracker]:
    """Start tracking of task in-use for the host integration.

    Tracking is skipped in headless mode, in farm jobs and in automated
    tests.

    Args:
        host (AbstractHost): Installed host integration.

    Returns:
        Optional[TaskUsageTracker]: Tracker or None if tracking is skipped.

    """
    global _tracker

    if _tracker is not None:
        return _tracker

    if (
        is_headless_mode_enabled()
        or is_in_tests()
        or any(os.environ.get(key) == "1" for key in FARM_JOB_ENV_KEYS)
    ):
        return None

    # Sessions confirmed by the user before the application was launched
    _acknowledged_session_ids.update(
        session_id
        for session_id in os.environ.get(
            ACKNOWLEDGED_SESSIONS_ENV_KEY, ""
        ).split(",")
        if session_id
    )

    _tracker = tracker = TaskUsageTracker(host)
    for topic in (
        "taskChanged",
        "workfile.opened",
        "workfile.saved",
        # Topics emitted by host integrations from native callbacks of
        #   the application
        "open",
        "save",
    ):
        register_event_callback(topic, tracker.sync)

    atexit.register(_on_exit)
    _connect_qt_quit()

    tracker.sync()
    return tracker


def uninstall_task_usage_tracker() -> None:
    """Release claimed task and stop the tracking."""
    global _tracker

    tracker, _tracker = _tracker, None
    if tracker is not None:
        tracker.release()
