"""Task in-use tracking (advisory task locking).

A session that works on a task registers itself in the task entity data
on AYON server. Other users can then be notified that somebody is already
working on the task before they open a workfile of the task.

The information is advisory. It never blocks anybody from working on the
task and a task can be used by multiple sessions at the same time.

The sessions are stored as a list under 'TASK_USAGE_DATA_KEY' key in the
task data. Sessions that did not update for longer than the stale timeout
are ignored and are removed with the next update of the task data, so
sessions of crashed applications do not stay on the task forever.
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

TASK_USAGE_DATA_KEY = "inUse"
DEFAULT_STALE_TIMEOUT_HOURS = 8.0
# Do not update the task more often if nothing but the time did change
REFRESH_INTERVAL_SECONDS = 5 * 60


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

    profiles = (
        project_settings
        ["core"]
        ["tools"]
        ["Workfiles"]
        .get("task_in_use_profiles")
    )
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
    value = task_data.get(TASK_USAGE_DATA_KEY)
    if not isinstance(value, list):
        return []
    items = []
    for item_data in value:
        item = TaskUsageItem.from_data(item_data)
        if item is not None:
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


def add_session_item(
    items: list[TaskUsageItem], new_item: TaskUsageItem
) -> list[TaskUsageItem]:
    """Add or update a session in sessions of a task.

    Time when the session was opened is kept if the session is already in
    the items. Other sessions of the same user in the same host on the same
    machine are removed. They are considered leftovers of a crashed
    application.

    Args:
        items (list[TaskUsageItem]): Sessions stored on a task.
        new_item (TaskUsageItem): Session to add.

    Returns:
        list[TaskUsageItem]: New list of sessions.

    """
    output = []
    for item in items:
        if item.session_id == new_item.session_id:
            new_item = replace(new_item, opened_at=item.opened_at)
            continue
        if (
            item.username == new_item.username
            and item.site_id == new_item.site_id
            and item.host_name == new_item.host_name
        ):
            continue
        output.append(item)
    output.append(new_item)
    return output


def remove_session_item(
    items: list[TaskUsageItem], session_id: str
) -> list[TaskUsageItem]:
    """Remove a session from sessions of a task."""
    return [item for item in items if item.session_id != session_id]


def filter_other_users_items(
    items: list[TaskUsageItem], username: str, session_id: str
) -> list[TaskUsageItem]:
    """Sessions the user should be notified about.

    Sessions of the user are never returned. Nothing is returned if the
    passed session is already registered on the task, in that case the user
    already did confirm that wants to work on the task.

    Args:
        items (list[TaskUsageItem]): Active sessions of a task.
        username (str): Current username.
        session_id (str): Current session id.

    Returns:
        list[TaskUsageItem]: Sessions of other users.

    """
    if any(item.session_id == session_id for item in items):
        return []
    return [item for item in items if item.username != username]


def _get_session_id() -> str:
    # Avoid circular import
    from ayon_core.pipeline.context_tools import get_process_id

    return get_process_id()


def _update_task_usage(
    project_name: str,
    task_id: str,
    stale_timeout_hours: float,
    new_item: Optional[TaskUsageItem] = None,
    remove_session_id: Optional[str] = None,
) -> None:
    """Update sessions on a task.

    Task data are fetched right before the update to lower the chance of
    overriding changes of somebody else. Stale sessions are removed.
    """
    task_entity = ayon_api.get_task_by_id(
        project_name, task_id, fields={"id", "data"}
    )
    if not task_entity:
        return

    task_data = task_entity.get("data") or {}
    current_value = task_data.get(TASK_USAGE_DATA_KEY)
    items = filter_active_items(
        parse_task_usage_items(task_data), stale_timeout_hours
    )
    if remove_session_id is not None:
        items = remove_session_item(items, remove_session_id)
    if new_item is not None:
        items = add_session_item(items, new_item)

    new_value = [item.to_data() for item in items]
    if new_value == (current_value or []):
        return

    # Whole data are sent with list value under single key, that way it
    #   does not matter if server does replace or merge the data.
    task_data[TASK_USAGE_DATA_KEY] = new_value
    ayon_api.update_task(project_name, task_id, data=task_data)


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

    Returns empty list if current process is already registered on the task.

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
        _get_session_id(),
    )


def claim_task(
    project_name: str,
    task_id: str,
    *,
    workfile: Optional[str] = None,
    host_name: Optional[str] = None,
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS,
) -> None:
    """Register current process as working on a task.

    Can be called repeatedly to update the workfile and time of the last
    activity.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        workfile (Optional[str]): Filename of the opened workfile.
        host_name (Optional[str]): Name of host integration.
        stale_timeout_hours (float): Sessions without an update for more
            than this amount of hours are removed from the task.

    """
    now = _get_now().isoformat()
    item = TaskUsageItem(
        session_id=_get_session_id(),
        username=get_ayon_username(),
        machine=socket.gethostname(),
        site_id=get_local_site_id(),
        host_name=host_name,
        workfile=workfile,
        opened_at=now,
        updated_at=now,
    )
    _update_task_usage(
        project_name, task_id, stale_timeout_hours, new_item=item
    )


def release_task(
    project_name: str,
    task_id: str,
    *,
    stale_timeout_hours: float = DEFAULT_STALE_TIMEOUT_HOURS,
) -> None:
    """Unregister current process from a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        stale_timeout_hours (float): Sessions without an update for more
            than this amount of hours are removed from the task.

    """
    _update_task_usage(
        project_name,
        task_id,
        stale_timeout_hours,
        remove_session_id=_get_session_id(),
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

    Failures are only logged. The tracker must never break host callbacks.

    Args:
        host (AbstractHost): Host integration.

    """
    def __init__(self, host):
        self._host = host
        self._claimed: Optional[_TaskContext] = None
        self._claimed_workfile: Optional[str] = None
        self._last_update: float = 0.0
        self._context_cache: dict[tuple, Optional[_TaskContext]] = {}

    def sync(self) -> None:
        """Synchronize the task registration with current host context."""
        try:
            self._sync()
        except Exception:
            log.warning("Failed to update task in-use data.", exc_info=True)

    def release(self) -> None:
        """Unregister from the claimed task."""
        claimed, self._claimed = self._claimed, None
        if claimed is None:
            return
        try:
            release_task(
                claimed.project_name,
                claimed.task_id,
                stale_timeout_hours=claimed.settings.stale_timeout_hours,
            )
        except Exception:
            log.warning("Failed to release task in-use data.", exc_info=True)

    def _sync(self) -> None:
        context = self._get_task_context()
        workfile = self._get_workfile_name()

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

        now = time.monotonic()
        if (
            claimed is not None
            and workfile == self._claimed_workfile
            and now - self._last_update < REFRESH_INTERVAL_SECONDS
        ):
            return

        claim_task(
            context.project_name,
            context.task_id,
            workfile=workfile,
            host_name=getattr(self._host, "name", None),
            stale_timeout_hours=context.settings.stale_timeout_hours,
        )
        self._claimed = context
        self._claimed_workfile = workfile
        self._last_update = now

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

    Tracking is skipped in headless mode and in automated tests.

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
        or os.environ.get("AYON_REMOTE_PUBLISH")
    ):
        return None

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
