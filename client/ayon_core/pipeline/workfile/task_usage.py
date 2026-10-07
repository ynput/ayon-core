"""Task in-use tracking (advisory task locking).

A session that works on a task registers itself on AYON server. Other users
can then be notified that somebody is already working on the task before
they open a workfile of the task.

The information is advisory. It never blocks anybody from working on the
task and a task can be used by multiple sessions at the same time.

Sessions are stored by server part of the core addon in Redis with a time
to live. Nothing is stored on the task entity, so a session does not change
the task, does not create events and the user does not need permissions to
update the task. Timestamps of sessions are filled by the server.

A session must report itself to the server (heartbeat) to stay alive.
The heartbeat is sent from a background thread a few times per the time
to live, so sessions of crashed applications expire on their own.

The endpoints are not available if the server runs older version of the
core addon. In that case the tracking is disabled and nothing is reported.
"""
from __future__ import annotations

import atexit
import datetime
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, asdict, fields, replace
from typing import Any, Iterable, Optional

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
from ayon_core.version import __version__

log = logging.getLogger(__name__)

ADDON_NAME = "core"

DEFAULT_SESSION_TIMEOUT_MINUTES = 5.0
# Limits of time to live of a session on the server
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 60 * 60
# Session survives a few missed heartbeats, e.g. when the application is
#   busy or the server is not available for a moment
HEARTBEATS_PER_TTL = 3
# Do not try to reach the server for some time after a failed request of
#   the tracker, to not slow down every save of a workfile
RETRY_INTERVAL_SECONDS = 5 * 60

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


class TaskUsageNotSupportedError(Exception):
    """AYON server does not have task in-use endpoints of the core addon."""


@dataclass
class TaskUsageSettings:
    """Task in-use settings for a context.

    Attributes:
        enabled (bool): Task in-use tracking is enabled for the context.
        session_timeout_minutes (float): A session that did not report
            itself to the server for this amount of minutes is removed.

    """
    enabled: bool = False
    session_timeout_minutes: float = DEFAULT_SESSION_TIMEOUT_MINUTES

    @property
    def ttl_seconds(self) -> int:
        """Time to live of a session on the server."""
        return int(max(
            MIN_TTL_SECONDS,
            min(MAX_TTL_SECONDS, self.session_timeout_minutes * 60),
        ))

    @property
    def heartbeat_interval(self) -> float:
        """Seconds between heartbeats of a session."""
        return self.ttl_seconds / HEARTBEATS_PER_TTL


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
            to work on the task. Filled by the server.
        updated_at (str): UTC time in ISO format of the last activity,
            e.g. opened or saved workfile. Filled by the server.

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
        """Create item from data created with 'to_data'.

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

    @classmethod
    def from_server_data(cls, data: Any) -> Optional[TaskUsageItem]:
        """Create item from session data received from the server.

        Returns:
            Optional[TaskUsageItem]: Item or None if data are not valid.

        """
        if not isinstance(data, dict):
            return None
        return cls.from_data({
            "session_id": data.get("sessionId"),
            "username": data.get("username"),
            "machine": data.get("machine"),
            "site_id": data.get("siteId"),
            "host_name": data.get("hostName"),
            "workfile": data.get("workfile"),
            "opened_at": data.get("openedAt"),
            "updated_at": data.get("updatedAt"),
        })

    def to_server_data(self) -> dict[str, Any]:
        """Data of the session sent to the server.

        Username and timestamps are filled by the server.
        """
        return {
            "machine": self.machine,
            "siteId": self.site_id,
            "hostName": self.host_name,
            "workfile": self.workfile,
        }

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
        session_timeout_minutes=profile.get(
            "session_timeout_minutes", DEFAULT_SESSION_TIMEOUT_MINUTES
        ),
    )


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


# 'False' when the server does not have the endpoints
_endpoints_supported: Optional[bool] = None


def is_task_usage_supported() -> bool:
    """Server did not report that task in-use endpoints are missing."""
    return _endpoints_supported is not False


def _get_endpoint(project_name: str, *subpaths: str) -> str:
    return ayon_api.get_addon_endpoint(
        ADDON_NAME, __version__, "projects", project_name, "taskInUse",
        *subpaths
    )


def _request(method: str, endpoint: str, **kwargs: Any) -> Any:
    """Call task in-use endpoint of the core addon.

    Raises:
        TaskUsageNotSupportedError: The server does not have the endpoints.

    """
    global _endpoints_supported

    if _endpoints_supported is False:
        raise TaskUsageNotSupportedError(
            "Task in-use endpoints are not available on the server."
        )

    response = getattr(ayon_api, method)(endpoint, **kwargs)
    # The endpoints do not use status 404 for their own responses
    if response.status_code == 404:
        _endpoints_supported = False
        log.warning(
            "Task in-use notification is disabled. AYON server does not"
            " have task in-use endpoints of '%s' addon version '%s',"
            " the server addon is probably older than the client.",
            ADDON_NAME,
            __version__,
        )
        raise TaskUsageNotSupportedError(
            "Task in-use endpoints are not available on the server."
        )
    response.raise_for_status()
    _endpoints_supported = True
    return response.data


def _parse_server_items(sessions: Any) -> list[TaskUsageItem]:
    if not isinstance(sessions, list):
        return []
    items = []
    for session in sessions:
        item = TaskUsageItem.from_server_data(session)
        if item is not None:
            items.append(item)
    return items


def get_task_usage_items(
    project_name: str,
    task_id: str,
) -> list[TaskUsageItem]:
    """Get active sessions working on a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.

    Returns:
        list[TaskUsageItem]: Active sessions of the task. Empty list if
            the server does not support task in-use tracking.

    """
    try:
        data = _request("get", _get_endpoint(project_name, task_id))
    except TaskUsageNotSupportedError:
        return []
    return _parse_server_items((data or {}).get("sessions"))


def get_tasks_usage_items(
    project_name: str,
    task_ids: Iterable[str],
) -> dict[str, list[TaskUsageItem]]:
    """Get active sessions working on multiple tasks.

    Args:
        project_name (str): Project name.
        task_ids (Iterable[str]): Task ids.

    Returns:
        dict[str, list[TaskUsageItem]]: Active sessions by task id. Each
            passed task id is in the output.

    """
    output: dict[str, list[TaskUsageItem]] = {
        task_id: [] for task_id in task_ids
    }
    if not output:
        return output
    try:
        data = _request(
            "post",
            _get_endpoint(project_name, "query"),
            taskIds=list(output),
        )
    except TaskUsageNotSupportedError:
        return output

    tasks = (data or {}).get("tasks")
    if isinstance(tasks, dict):
        for task_id, sessions in tasks.items():
            if task_id in output:
                output[task_id] = _parse_server_items(sessions)
    return output


def get_other_users_task_usage_items(
    project_name: str,
    task_id: str,
) -> list[TaskUsageItem]:
    """Get sessions of other users working on a task.

    Sessions acknowledged with 'acknowledge_task_usage_items' are skipped.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.

    Returns:
        list[TaskUsageItem]: Active sessions of other users.

    """
    return filter_other_users_items(
        get_task_usage_items(project_name, task_id),
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
    # Times are only informative, the server does fill its own
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
    ttl: Optional[int] = None,
    heartbeat: bool = False,
) -> list[TaskUsageItem]:
    """Register or refresh a session as working on a task.

    The session is removed by the server if it is not refreshed with
    another call in the time to live.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        item (TaskUsageItem): Session to register.
        ttl (Optional[int]): Time to live of the session in seconds.
        heartbeat (bool): Only keep the session alive, the time of last
            activity of the session is not changed.

    Returns:
        list[TaskUsageItem]: Other active sessions working on the task.

    Raises:
        TaskUsageNotSupportedError: The server does not have the endpoints.

    """
    if ttl is None:
        ttl = TaskUsageSettings().ttl_seconds
    data = _request(
        "put",
        _get_endpoint(project_name, task_id, item.session_id),
        ttl=ttl,
        heartbeat=heartbeat,
        **item.to_server_data()
    )
    return [
        other_item
        for other_item in _parse_server_items((data or {}).get("sessions"))
        if other_item.session_id != item.session_id
    ]


def update_task_session(
    project_name: str,
    task_id: str,
    item: TaskUsageItem,
    ttl: Optional[int] = None,
    heartbeat: bool = False,
) -> None:
    """Update a session on a task and keep it alive.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        item (TaskUsageItem): Session to update.
        ttl (Optional[int]): Time to live of the session in seconds.
        heartbeat (bool): Only keep the session alive, the time of last
            activity of the session is not changed.

    Raises:
        TaskUsageNotSupportedError: The server does not have the endpoints.

    """
    claim_task(project_name, task_id, item, ttl, heartbeat)


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
    try:
        _request(
            "delete", _get_endpoint(project_name, task_id, session_id)
        )
    except TaskUsageNotSupportedError:
        pass


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

    Claimed task is kept alive on the server with heartbeats sent from
    a background thread, see 'start_heartbeat'. The thread does not touch
    the host integration.

    When a task is claimed and other users are working on it, the user is
    notified about them, unless the user did already confirm them, e.g. in
    the Workfiles tool.

    Failures are only logged. The tracker must never break host callbacks.
    The tracker disables itself if the server does not support task in-use
    tracking.

    Args:
        host (AbstractHost): Host integration.

    """
    def __init__(self, host):
        self._host = host
        self._claimed: Optional[_TaskContext] = None
        self._item: Optional[TaskUsageItem] = None
        self._last_update: float = 0.0
        self._retry_after: float = 0.0
        self._disabled: bool = False
        self._context_cache: dict[tuple, Optional[_TaskContext]] = {}
        # Claimed task is accessed from the heartbeat thread
        self._lock = threading.RLock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

    @property
    def is_disabled(self) -> bool:
        """The server does not support task in-use tracking."""
        return self._disabled

    def sync(self) -> None:
        """Synchronize the task registration with current host context.

        Is not processed for some time after a failure, e.g. when server is
        not available, to not slow down every save of a workfile.
        """
        if self._disabled or time.monotonic() < self._retry_after:
            return
        other_items = []
        try:
            with self._lock:
                other_items = self._sync()
        except TaskUsageNotSupportedError:
            self._disable()
        except Exception:
            self._retry_after = time.monotonic() + RETRY_INTERVAL_SECONDS
            log.warning("Failed to update task in-use data.", exc_info=True)

        # Sessions stay unconfirmed if the user could not be notified, the
        #   user is asked about them when opens a workfile of the task
        if other_items and self._notify(other_items):
            acknowledge_task_usage_items(other_items)

    def release(self) -> None:
        """Unregister from the claimed task."""
        with self._lock:
            claimed, self._claimed = self._claimed, None
            item, self._item = self._item, None
            if claimed is None or item is None:
                return
            try:
                release_task(
                    claimed.project_name, claimed.task_id, item.session_id
                )
            except Exception:
                log.warning(
                    "Failed to release task in-use data.", exc_info=True
                )

    def heartbeat(self) -> None:
        """Keep the session on the claimed task alive.

        Can be called from any thread. Nothing is sent if the session was
        updated a moment ago.
        """
        with self._lock:
            claimed = self._claimed
            item = self._item
            if self._disabled or claimed is None or item is None:
                return

            now = time.monotonic()
            interval = claimed.settings.heartbeat_interval
            if now - self._last_update < interval / 2:
                return
            try:
                update_task_session(
                    claimed.project_name,
                    claimed.task_id,
                    item,
                    claimed.settings.ttl_seconds,
                    heartbeat=True,
                )
                self._last_update = now
            except TaskUsageNotSupportedError:
                self._disable()
            except Exception:
                # Server may be temporarily not available
                log.debug(
                    "Failed to send task in-use heartbeat.", exc_info=True
                )

    def start_heartbeat(self) -> None:
        """Start a background thread sending heartbeats.

        The thread is a daemon, so it does not block exit of the process.
        """
        if self._heartbeat_thread is not None or self._disabled:
            return
        self._heartbeat_stop = stop_event = threading.Event()
        self._heartbeat_thread = thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop_event,),
            name="ayon-task-in-use-heartbeat",
            daemon=True,
        )
        thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread, does not wait for the thread."""
        self._heartbeat_thread = None
        self._heartbeat_stop.set()

    def _heartbeat_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._get_heartbeat_interval()):
            try:
                self.heartbeat()
            except Exception:
                log.debug("Task in-use heartbeat failed.", exc_info=True)

    def _get_heartbeat_interval(self) -> float:
        claimed = self._claimed
        if claimed is None:
            return TaskUsageSettings().heartbeat_interval
        return claimed.settings.heartbeat_interval

    def _disable(self) -> None:
        self._disabled = True
        self._claimed = None
        self._item = None
        self.stop_heartbeat()

    def _sync(self) -> list[TaskUsageItem]:
        """Synchronize the registration.

        Returns:
            list[TaskUsageItem]: Sessions of other users the user should be
                notified about.

        """
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
            return []

        workfile = self._get_workfile_name()
        now = time.monotonic()
        if claimed is None:
            other_items = self._claim(context, workfile)
            self._last_update = now
            return other_items

        # The time based refresh is a fallback for applications where
        #   the heartbeat thread is not processed
        if (
            workfile != self._item.workfile
            or now - self._last_update >= context.settings.heartbeat_interval
        ):
            item = replace(self._item, workfile=workfile)
            update_task_session(
                context.project_name,
                context.task_id,
                item,
                context.settings.ttl_seconds,
            )
            self._item = item
            self._last_update = now
        return []

    def _claim(
        self, context: _TaskContext, workfile: Optional[str]
    ) -> list[TaskUsageItem]:
        item = create_session_item(
            workfile, getattr(self._host, "name", None)
        )
        other_items = claim_task(
            context.project_name,
            context.task_id,
            item,
            context.settings.ttl_seconds,
        )
        self._claimed = context
        self._item = item

        return filter_other_users_items(
            other_items, item.username, _acknowledged_session_ids
        )

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
        _tracker.stop_heartbeat()
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
    tracker.start_heartbeat()
    return tracker


def uninstall_task_usage_tracker() -> None:
    """Release claimed task and stop the tracking."""
    global _tracker

    tracker, _tracker = _tracker, None
    if tracker is not None:
        tracker.stop_heartbeat()
        tracker.release()
