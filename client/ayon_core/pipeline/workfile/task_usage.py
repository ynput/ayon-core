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
The heartbeat is sent a few times per the time to live, so sessions of
crashed applications expire on their own.

Which workfiles are opened in the application is defined by the host
integration, see 'IWorkfileHost.get_workfiles_in_use'. By default it is
the current workfile in the current context. Each opened workfile has its
own session, all of them are released when the application is closed.

Callbacks of the application do not wait for the server. Session of the
application is handled by 'TaskUsageTracker' in a background thread, the
main thread only passes current context to it. A notice about other users
is passed to callbacks registered by the host integration, which shows it
in its own thread, see 'register_task_in_use_notice_callback'. Without
a callback the user is asked in the launcher and in the Workfiles tool.
"""
from __future__ import annotations

import atexit
import datetime
import hashlib
import logging
import os
import socket
import threading
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable

import ayon_api

from ayon_core.host import AbstractHost, WorkfileInUse
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
# Session survives a few missed heartbeats, e.g. when the application is
#   busy or the server is not available for a moment
HEARTBEATS_PER_TTL = 3
# Do not wait for the server as long as for other requests, the requests
#   are also sent before a workfile is opened and on application launch
REQUEST_TIMEOUT_SECONDS = 5.0
# Opened or saved workfile is reported as activity of the session, but not
#   more often if the workfile did not change
ACTIVITY_INTERVAL_SECONDS = 30.0
# Scheduled context that was not processed for this time means that the
#   background thread is not processed by the application
STARVED_THREAD_SECONDS = 10.0
# How long is exit of the application blocked to release the task
EXIT_TIMEOUT_SECONDS = 3.0

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
        session_timeout_minutes (float): A session that did not report
            itself to the server for this amount of minutes is removed.

    """
    enabled: bool = False
    session_timeout_minutes: float = DEFAULT_SESSION_TIMEOUT_MINUTES

    @property
    def ttl_seconds(self) -> int:
        """Time to live of a session on the server."""
        return int(self.session_timeout_minutes * 60)

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
        machine (str | None): Name of the machine.
        site_id (str | None): AYON site id of the machine.
        host_name (str | None): Name of host integration, e.g. 'maya'.
        workfile (str | None): Filename of the workfile opened in the
            session.
        opened_at (str): UTC time in ISO format when the session started
            to work on the task. Filled by the server.
        updated_at (str): UTC time in ISO format of the last activity,
            e.g. opened or saved workfile. Filled by the server.
        full_name (str | None): Full name of the user. Filled by the
            server.

    """
    session_id: str
    username: str
    machine: str | None
    site_id: str | None
    host_name: str | None
    workfile: str | None
    opened_at: str
    updated_at: str
    full_name: str | None = None

    def to_data(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> TaskUsageItem:
        return cls(**data)

    @classmethod
    def from_server_data(cls, data: dict[str, Any]) -> TaskUsageItem:
        """Create item from session data received from the server."""
        return cls(
            session_id=data["sessionId"],
            username=data["username"],
            machine=data["machine"],
            site_id=data["siteId"],
            host_name=data["hostName"],
            workfile=data["workfile"],
            opened_at=data["openedAt"],
            updated_at=data["updatedAt"],
            full_name=data["fullName"],
        )

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

    def get_opened_at(self) -> datetime.datetime | None:
        return _parse_time(self.opened_at)

    def get_updated_at(self) -> datetime.datetime | None:
        return _parse_time(self.updated_at)


def _get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_time(value: Any) -> datetime.datetime | None:
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
        ["task_in_use_profiles"]
    )


def is_task_usage_enabled_in_project(
    project_name: str,
    project_settings: dict[str, Any] | None = None,
) -> bool:
    """Task in-use tracking can be enabled for some context of a project.

    Can be used to skip queries of entities needed to find out if the
    tracking is enabled for specific context.

    Args:
        project_name (str): Project name.
        project_settings (dict[str, Any] | None): Prepared project
            settings.

    Returns:
        bool: Project has at least one enabled profile.

    """
    if project_settings is None:
        project_settings = get_project_settings(project_name)
    return any(
        profile["enabled"]
        for profile in _get_profiles(project_settings)
    )


def get_task_usage_settings(
    project_name: str,
    host_name: str,
    task_type: str,
    task_name: str,
    project_settings: dict[str, Any] | None = None,
) -> TaskUsageSettings:
    """Task in-use settings for a context.

    Args:
        project_name (str): Project name.
        host_name (str): Host name.
        task_type (str): Task type.
        task_name (str): Task name.
        project_settings (dict[str, Any] | None): Prepared project
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
        session_timeout_minutes=profile["session_timeout_minutes"],
    )


def filter_other_users_items(
    items: list[TaskUsageItem],
    username: str,
    acknowledged_session_ids: set[str] | None = None,
) -> list[TaskUsageItem]:
    """Sessions the user should be notified about.

    Sessions of the user and sessions the user was already notified about
    are not returned.

    Args:
        items (list[TaskUsageItem]): Active sessions of a task.
        username (str): Current username.
        acknowledged_session_ids (set[str] | None): Sessions the user
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


def _get_session_id() -> str:
    # Avoid circular import
    from ayon_core.pipeline.context_tools import get_process_id

    return get_process_id()


def get_workfile_session_id(key: str = "") -> str:
    """Session id of a workfile opened in current process.

    Args:
        key (str): Identifier of the opened workfile in the application,
            see 'WorkfileInUse'. Empty string is used by applications
            that have opened only one workfile.

    Returns:
        str: Session id.

    """
    session_id = _get_session_id()
    if not key:
        return session_id
    key_hash = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{session_id}-{key_hash}"


def _get_endpoint(project_name: str, *subpaths: str) -> str:
    # NOTE 'ayon_api.get_addon_endpoint' can't be used, it fails when
    #   subpaths are passed
    return "/".join((
        "addons", ADDON_NAME, __version__,
        "projects", project_name, "taskInUse",
        *subpaths
    ))


def _request(
    method: str, endpoint: str, data: dict[str, Any] | None = None
) -> Any:
    """Call task in-use endpoint of the core addon."""
    kwargs: dict[str, Any] = {"timeout": REQUEST_TIMEOUT_SECONDS}
    if data is not None:
        kwargs["json"] = data
    response = getattr(ayon_api, f"raw_{method}")(endpoint, **kwargs)
    response.raise_for_status()
    return response.data


def _parse_server_items(data: dict[str, Any]) -> list[TaskUsageItem]:
    return [
        TaskUsageItem.from_server_data(session)
        for session in data["sessions"]
    ]


def get_task_usage_items(
    project_name: str,
    task_id: str,
) -> list[TaskUsageItem]:
    """Get active sessions working on a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.

    Returns:
        list[TaskUsageItem]: Active sessions of the task.

    """
    return _parse_server_items(
        _request("get", _get_endpoint(project_name, task_id))
    )


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
    workfile: str | None,
    host_name: str,
    session_id: str,
) -> TaskUsageItem:
    """Create session item of current process.

    Args:
        workfile (str | None): Filename of the opened workfile.
        host_name (str): Name of host integration.
        session_id (str): Session id, see 'get_workfile_session_id'.

    Returns:
        TaskUsageItem: Session of current process.

    """
    # Times are only informative, the server does fill its own
    now = _get_now().isoformat()
    return TaskUsageItem(
        session_id=session_id,
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
    ttl: int,
    heartbeat: bool = False,
) -> list[TaskUsageItem]:
    """Register or refresh a session as working on a task.

    The session is removed by the server if it is not refreshed with
    another call in the time to live.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        item (TaskUsageItem): Session to register.
        ttl (int): Time to live of the session in seconds.
        heartbeat (bool): Only keep the session alive, the time of last
            activity of the session is not changed.

    Returns:
        list[TaskUsageItem]: Other active sessions working on the task.

    """
    data = _request(
        "put",
        _get_endpoint(project_name, task_id, item.session_id),
        dict(item.to_server_data(), ttl=ttl, heartbeat=heartbeat),
    )
    return [
        other_item
        for other_item in _parse_server_items(data)
        if other_item.session_id != item.session_id
    ]


def release_task(
    project_name: str,
    task_id: str,
    session_id: str,
) -> None:
    """Unregister a session from a task.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        session_id (str): Session id.

    """
    _request("delete", _get_endpoint(project_name, task_id, session_id))


@dataclass
class _TaskContext:
    project_name: str
    task_id: str
    settings: TaskUsageSettings


@dataclass(frozen=True)
class _HostWorkfile:
    """Workfile opened in the application, captured in the main thread."""
    project_name: str | None
    folder_path: str | None
    task_name: str | None
    workfile: str | None
    key: str = ""


@dataclass
class _ClaimedSession:
    """Session of an opened workfile registered on the server."""
    context: _TaskContext
    item: TaskUsageItem
    last_update: float
    last_activity: float


_notice_callbacks: list[Callable[[list[TaskUsageItem]], None]] = []


def register_task_in_use_notice_callback(
    callback: Callable[[list[TaskUsageItem]], None]
) -> None:
    """Register callback called when the claimed task is in use.

    The callback is a way how a frontend can show a notice to the user.
    It receives sessions of other users working on the task. The task is
    already in use by current process at this point, e.g. the application
    was launched with a workfile, so the user can only be informed.

    Sessions passed to a callback are not passed again and the user is not
    asked about them in the Workfiles tool.

    Host integration should register the callback in its 'install', the
    tracking is started by 'install_host' after that. Integrations based
    on Qt can use 'install_task_in_use_notifier' from
    'ayon_core.tools.workfiles.widgets.task_in_use_dialog'.

    Warning:
        The callback is called from a background thread. It must not
        block and must not touch the application or its UI directly. It
        has to pass the sessions to the thread where it can show them
        on its own, e.g. with a queued Qt signal.

    Args:
        callback (Callable[[list[TaskUsageItem]], None]): Callback to
            register.

    """
    if callback not in _notice_callbacks:
        _notice_callbacks.append(callback)


class TaskUsageTracker:
    """Keep workfiles opened in the application registered on their tasks.

    The tracker follows workfiles opened in the application, which are
    received from the host integration, see
    'IWorkfileHost.get_workfiles_in_use'. By default it is the current
    workfile in the current context.

    Task of a workfile is claimed when the workfile appears, e.g. when
    context changes or a workfile is opened, and is released when the
    workfile is not opened anymore or the process ends. Claimed tasks are
    kept alive on the server with heartbeats.

    Callbacks of the application must not wait for the server, so the work
    is split to 2 parts:
        - 'sync' is called from the callbacks in the main thread. It only
            reads opened workfiles from the host integration and schedules
            them, without any request to the server.
        - 'process' does all requests to the server. It is called from
            a background thread, see 'start'. The thread sleeps most of
            the time and never touches the host integration.

    When a task is claimed and other users are working on it, callbacks
    registered with 'register_task_in_use_notice_callback' are called,
    unless the user did already confirm the sessions, e.g. in the launcher
    or in the Workfiles tool.

    Failures are only logged. The tracker must never break host callbacks.

    Args:
        host (AbstractHost): Host integration.

    """
    def __init__(self, host: AbstractHost):
        self._host = host
        self._host_name: str = host.name

        # Context scheduled in main thread for the background thread
        self._lock = threading.Lock()
        self._scheduled: tuple[_HostWorkfile, ...] | None = None
        self._is_scheduled: bool = False
        self._scheduled_at: float = 0.0

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

        # Only one thread can talk to the server at a time
        self._process_lock = threading.Lock()
        # Attributes below are changed only during the processing
        self._state: tuple[_HostWorkfile, ...] | None = None
        # Claimed sessions by key of opened workfile
        self._sessions: dict[str, _ClaimedSession] = {}
        self._failed: bool = False
        self._context_cache: dict[tuple, _TaskContext | None] = {}

    def sync(self) -> None:
        """Schedule synchronization with current context of the host.

        Should be called from the main thread of the application, e.g.
        from callbacks of the host integration. Does not wait for the
        server, the context is processed in the background thread.
        """
        try:
            state = self._get_host_state()
        except Exception:
            log.warning(
                "Failed to receive context for task in-use tracking.",
                exc_info=True,
            )
            return
        self._schedule(state)

    def process(self) -> None:
        """Apply scheduled context on the server and keep session alive.

        Does requests to the server, so it is called from the background
        thread. Can be called from any thread, e.g. if the thread is not
        used. Nothing happens if other thread is processing right now.
        """
        if not self._process_lock.acquire(blocking=False):
            return
        try:
            self._process()
            self._failed = False
        except Exception:
            # Server may be temporarily not available, is repeated later
            log_method = log.debug if self._failed else log.warning
            log_method("Failed to update task in-use data.", exc_info=True)
            self._failed = True
        finally:
            self._process_lock.release()

    def start(self) -> None:
        """Start background thread that does the processing.

        The thread is a daemon, so it does not block exit of the process.
        """
        if self._thread is not None:
            return
        self._stop_event = stop_event = threading.Event()
        self._thread = thread = threading.Thread(
            target=self._run,
            args=(stop_event,),
            name="ayon-task-in-use",
            daemon=True,
        )
        thread.start()

    def stop(self) -> None:
        """Release all claimed tasks and stop the background thread.

        Can be called by the host integration on exit of the application.
        The tasks are released by the thread, which is awaited only for
        a moment, so a slow server does not block the exit. They are
        released in current thread if the thread was not started.
        """
        thread, self._thread = self._thread, None
        with self._lock:
            self._scheduled = None
            self._is_scheduled = True
            self._scheduled_at = time.monotonic()
        self._stop_event.set()
        self._wake_event.set()

        if thread is None:
            self.process()
        elif thread is not threading.current_thread():
            thread.join(EXIT_TIMEOUT_SECONDS)

    def _schedule(
        self, state: tuple[_HostWorkfile, ...] | None
    ) -> None:
        now = time.monotonic()
        with self._lock:
            # Background threads are not processed in some applications
            #   when Python code is not running in the main thread
            is_starved = (
                self._is_scheduled
                and self._thread is not None
                and now - self._scheduled_at >= STARVED_THREAD_SECONDS
                and not self._process_lock.locked()
            )
            if not self._is_scheduled:
                self._scheduled_at = now
            self._scheduled = state
            self._is_scheduled = True
        self._wake_event.set()

        if is_starved:
            log.debug(
                "Task in-use thread is not processed by the application."
                " Processing in current thread."
            )
            self.process()

    def _run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self._wake_event.wait(self._get_wait_seconds())
            self._wake_event.clear()
            self.process()
        # Release can be scheduled by 'stop' while a request is running
        self.process()

    def _get_wait_seconds(self) -> float:
        """Seconds until the next heartbeat or next try after a failure."""
        sessions = list(self._sessions.values())
        if not sessions:
            return TaskUsageSettings().heartbeat_interval
        now = time.monotonic()
        return min(
            (
                session.context.settings.heartbeat_interval
                if self._failed
                else max(
                    1.0,
                    session.context.settings.heartbeat_interval
                    - (now - session.last_update),
                )
            )
            for session in sessions
        )

    def _process(self) -> None:
        is_activity = False
        with self._lock:
            if self._is_scheduled:
                # Callback of the application without a change of opened
                #   workfiles is an activity, e.g. a saved workfile. It is
                #   not known which workfile it was, if there are more.
                is_activity = self._scheduled == self._state
                self._state = self._scheduled
                self._scheduled = None
                self._is_scheduled = False

        # Opened workfiles with enabled tracking by their key
        workfiles: dict[str, tuple[_TaskContext, str | None]] = {}
        for host_workfile in self._state or ():
            context = self._get_task_context(host_workfile)
            if context is not None:
                workfiles[host_workfile.key] = (
                    context, host_workfile.workfile
                )

        # Release workfiles that are not opened anymore or changed task
        for key, session in list(self._sessions.items()):
            context = workfiles.get(key, (None, None))[0]
            if (
                context is None
                or context.project_name != session.context.project_name
                or context.task_id != session.context.task_id
            ):
                self._release_session(key)

        # Sessions of other users the user was told about in this run
        notified_session_ids: set[str] = set()
        for key, (context, workfile) in workfiles.items():
            session = self._sessions.get(key)
            if session is None:
                self._claim(key, context, workfile, notified_session_ids)
                continue

            now = time.monotonic()
            item = session.item
            ttl = context.settings.ttl_seconds
            if workfile != item.workfile or (
                # Workfile was opened or saved, but do not report each save
                is_activity
                and now - session.last_activity >= ACTIVITY_INTERVAL_SECONDS
            ):
                item = replace(item, workfile=workfile)
                claim_task(
                    context.project_name, context.task_id, item, ttl
                )
                session.item = item
                session.last_update = session.last_activity = now

            elif (
                now - session.last_update
                >= context.settings.heartbeat_interval - 1.0
            ):
                claim_task(
                    context.project_name,
                    context.task_id,
                    item,
                    ttl,
                    heartbeat=True,
                )
                session.last_update = now

    def _release_session(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        try:
            release_task(
                session.context.project_name,
                session.context.task_id,
                session.item.session_id,
            )
        except Exception:
            # The session does expire on the server
            log.warning("Failed to release task in-use data.", exc_info=True)

    def _claim(
        self,
        key: str,
        context: _TaskContext,
        workfile: str | None,
        notified_session_ids: set[str],
    ) -> None:
        item = create_session_item(
            workfile, self._host_name, get_workfile_session_id(key)
        )
        other_items = claim_task(
            context.project_name,
            context.task_id,
            item,
            context.settings.ttl_seconds,
        )
        now = time.monotonic()
        self._sessions[key] = _ClaimedSession(context, item, now, now)

        other_items = [
            other_item
            for other_item in filter_other_users_items(
                other_items, item.username, _acknowledged_session_ids
            )
            if other_item.session_id not in notified_session_ids
        ]
        if other_items:
            notified_session_ids.update(
                other_item.session_id for other_item in other_items
            )
            self._notify(other_items)

    def _notify(self, items: list[TaskUsageItem]) -> None:
        """Notify user that other users are working on the claimed task.

        Is called from the background thread, so the sessions are only
        passed to registered callbacks. Sessions are acknowledged when
        a callback did receive them, the user is asked about them when
        opens a workfile of the task otherwise.
        """
        log.warning(
            "Task is in use by other users: %s",
            ", ".join(sorted({item.username for item in items})),
        )
        received = False
        for callback in list(_notice_callbacks):
            try:
                callback(list(items))
                received = True
            except Exception:
                log.debug(
                    "Failed to pass task in-use notice.", exc_info=True
                )
        if received:
            acknowledge_task_usage_items(items)

    def _get_workfile_filepath(self) -> str | None:
        get_current_workfile = getattr(
            self._host, "get_current_workfile", None
        )
        if get_current_workfile is None:
            return None
        return get_current_workfile() or None

    def _get_host_state(self) -> tuple[_HostWorkfile, ...]:
        """Workfiles opened in the application.

        Is called from the main thread.
        """
        get_workfiles_in_use = getattr(
            self._host, "get_workfiles_in_use", None
        )
        if get_workfiles_in_use is not None:
            workfiles_in_use = get_workfiles_in_use()
        else:
            # Host integration without workfiles interface
            context = self._host.get_current_context()
            workfiles_in_use = [
                WorkfileInUse(
                    context["project_name"],
                    context["folder_path"],
                    context["task_name"],
                    self._get_workfile_filepath(),
                )
            ]

        # Each key can be used only once
        workfiles_by_key = {}
        for workfile_in_use in workfiles_in_use or []:
            workfile = None
            if workfile_in_use.filepath:
                workfile = os.path.basename(workfile_in_use.filepath)
            key = str(workfile_in_use.key or "")
            workfiles_by_key[key] = _HostWorkfile(
                workfile_in_use.project_name,
                workfile_in_use.folder_path,
                workfile_in_use.task_name,
                workfile,
                key,
            )
        return tuple(workfiles_by_key.values())

    def _get_task_context(
        self, host_workfile: _HostWorkfile
    ) -> _TaskContext | None:
        """Task of opened workfile with enabled in-use tracking."""
        project_name = host_workfile.project_name
        folder_path = host_workfile.folder_path
        task_name = host_workfile.task_name
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
    ) -> _TaskContext | None:
        project_settings = get_project_settings(project_name)
        # Avoid queries of entities if the tracking is not used in project
        if not is_task_usage_enabled_in_project(
            project_name, project_settings
        ):
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
            self._host_name,
            task_entity["taskType"],
            task_entity["name"],
            project_settings,
        )
        if not settings.enabled:
            return None
        return _TaskContext(project_name, task_entity["id"], settings)


# Keep the tracker referenced, event callbacks are stored as weak references
_tracker: TaskUsageTracker | None = None


def _on_exit() -> None:
    if _tracker is not None:
        _tracker.stop()


def sync_task_usage() -> None:
    """Tell task in-use tracking that opened workfiles did change.

    Can be called by a host integration when workfiles opened in the
    application change in a way that is not known to AYON, e.g. when
    a document is closed. Should be called from the main thread of
    the application. Does not wait for the server.
    """
    tracker = _tracker
    if tracker is not None:
        tracker.sync()


def _is_used_in_host_project(host: AbstractHost) -> bool:
    """Project of the host integration has an enabled profile."""
    try:
        project_name = host.get_current_context()["project_name"]
        return bool(project_name) and is_task_usage_enabled_in_project(
            project_name
        )
    except Exception:
        log.debug(
            "Failed to find out if task in-use tracking is used.",
            exc_info=True,
        )
    return False


def install_task_usage_tracker(
    host: AbstractHost,
) -> TaskUsageTracker | None:
    """Start tracking of task in-use for the host integration.

    Is called by 'install_host' from the main thread of the application.
    Tracking is skipped in headless mode, in farm jobs and in automated
    tests.

    Nothing is started if project of the host integration does not have
    any enabled profile of task in-use notification, so the feature does
    not cost anything when it is not used.

    The tasks are released on exit with 'atexit', and when Qt application
    quits if the host uses 'install_task_in_use_notifier'. Other host
    integration of an application that does not call 'atexit' callbacks
    on exit should call 'uninstall_task_usage_tracker' on exit of the
    application. Otherwise the session expires after the session timeout.

    Args:
        host (AbstractHost): Installed host integration.

    Returns:
        TaskUsageTracker | None: Tracker or None if tracking is skipped.

    """
    global _tracker

    if _tracker is not None:
        return _tracker

    if (
        is_headless_mode_enabled()
        or is_in_tests()
        or any(os.environ.get(key) == "1" for key in FARM_JOB_ENV_KEYS)
        or not _is_used_in_host_project(host)
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
        "new",
        "open",
        "save",
    ):
        register_event_callback(topic, tracker.sync)

    atexit.register(_on_exit)

    tracker.sync()
    tracker.start()
    return tracker


def uninstall_task_usage_tracker() -> None:
    """Release claimed task and stop the tracking."""
    global _tracker

    tracker, _tracker = _tracker, None
    if tracker is not None:
        atexit.unregister(_on_exit)
        tracker.stop()
