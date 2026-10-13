"""Task in-use sessions (advisory task locking).

A session of a user working on a task is stored in Redis. The session must
be refreshed (heartbeat) to stay alive, so sessions of crashed applications
expire on their own.

Nothing is stored on the task entity, so the sessions do not change the
task, do not create events and a user does not need permissions to write
to the task. Any user with access to the project can use the endpoints.

Redis:
    Sessions of a task are stored in one hash. Field of the hash is
    a session id and the value is JSON with the session and the time when
    the session expires.

    A session writes and removes only its own field with atomic commands,
    which do not affect other fields. Multiple users can claim, refresh,
    release and list sessions of the same task at the same time without
    losing any of the sessions.

    Expired sessions are skipped when the sessions are listed. They are not
    removed from the hash, the whole hash is removed by Redis when none of
    the sessions was refreshed for 'REDIS_KEY_TTL'.
"""
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import Path

from ayon_server.api.dependencies import CurrentUser, ProjectName, TaskID
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel
from ayon_server.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from ayon_server.addons import BaseServerAddon

REDIS_NAMESPACE = "core-entity-lock"

DEFAULT_TTL = 5 * 60
MIN_TTL = 30
MAX_TTL = 60 * 60
# The hash must live at least as long as any of its sessions
REDIS_KEY_TTL = MAX_TTL
MAX_TASKS_PER_QUERY = 500

SESSION_ID_REGEX = r"^[a-zA-Z0-9_-]{1,64}$"
# Key of session data in Redis that is not part of the session model
EXPIRES_AT_KEY = "expiresAt"


class TaskSessionModel(OPModel):
    session_id: str = Field(..., title="Session ID")
    username: str = Field(..., title="User name")
    machine: str | None = Field(None, title="Machine name")
    site_id: str | None = Field(None, title="Site ID")
    host_name: str | None = Field(None, title="Host name", example="maya")
    workfile: str | None = Field(None, title="Workfile name")
    opened_at: str = Field(
        ...,
        title="Opened at",
        description="Server time when the session did claim the task",
    )
    updated_at: str = Field(
        ...,
        title="Updated at",
        description="Server time of last activity of the session",
    )


class ClaimTaskModel(OPModel):
    machine: str | None = Field(None, title="Machine name", max_length=255)
    site_id: str | None = Field(None, title="Site ID", max_length=255)
    host_name: str | None = Field(None, title="Host name", max_length=255)
    workfile: str | None = Field(None, title="Workfile name", max_length=1024)
    ttl: int = Field(
        DEFAULT_TTL,
        title="Time to live",
        description=(
            "Seconds after which the session expires if is not refreshed."
            f" The value is clamped to {MIN_TTL}-{MAX_TTL} seconds."
        ),
    )
    heartbeat: bool = Field(
        False,
        title="Heartbeat",
        description=(
            "Only keep the session alive. Time of last activity"
            " of an existing session is not changed."
        ),
    )


class TaskSessionsModel(OPModel):
    sessions: list[TaskSessionModel] = Field(
        default_factory=list,
        title="Sessions",
        description="Sessions that are working on the task",
    )


class ClaimTaskResponseModel(TaskSessionsModel):
    ttl: int = Field(..., title="Time to live of the session in seconds")


class TasksQueryModel(OPModel):
    task_ids: list[str] = Field(
        default_factory=list,
        title="Task IDs",
        max_items=MAX_TASKS_PER_QUERY,
    )


class TasksSessionsModel(OPModel):
    tasks: dict[str, list[TaskSessionModel]] = Field(
        default_factory=dict,
        title="Sessions by task ID",
        description="Tasks without sessions are not included",
    )


SessionID = Path(..., title="Session ID", regex=SESSION_ID_REGEX)


def _task_key(project_name: str, task_id: str) -> str:
    """Key of hash with sessions of a task, as 'Redis' helper stores it."""
    return f"{Redis.prefix}{REDIS_NAMESPACE}-{project_name}-task-{task_id}"


async def _get_redis_pool():
    if not Redis.connected:
        await Redis.connect()
    return Redis.redis_pool


def _parse_session(payload: Any) -> TaskSessionModel | None:
    """Session from a value of the hash, None if the session did expire."""
    if payload is None:
        return None
    try:
        data = json_loads(payload)
        if data.pop(EXPIRES_AT_KEY) <= time.time():
            return None
        return TaskSessionModel(**data)
    except Exception:
        return None


def _parse_sessions(payloads: dict[Any, Any]) -> list[TaskSessionModel]:
    """Sessions that did not expire from content of the hash."""
    sessions = [
        session
        for session in map(_parse_session, payloads.values())
        if session is not None
    ]
    sessions.sort(key=lambda session: (session.opened_at, session.session_id))
    return sessions


async def _get_sessions(
    project_name: str, task_id: str
) -> list[TaskSessionModel]:
    """Sessions of a task that did not expire."""
    pool = await _get_redis_pool()
    return _parse_sessions(
        await pool.hgetall(_task_key(project_name, task_id))
    )


async def _ensure_task_exists(project_name: str, task_id: str) -> None:
    row = await Postgres.fetchrow(
        f"SELECT id FROM project_{project_name}.tasks WHERE id = $1",
        task_id,
    )
    if row is None:
        # Not found (404) is not used, so clients can use it to detect
        #   that the endpoints are not available
        raise BadRequestException(f"Task {task_id} does not exist")


async def claim_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    payload: ClaimTaskModel,
    session_id: str = SessionID,
) -> ClaimTaskResponseModel:
    """Register or refresh a session working on a task.

    The session expires if is not refreshed in the time to live. Returns
    all sessions working on the task, including the claimed one.
    """
    pool = await _get_redis_pool()
    task_key = _task_key(project_name, task_id)
    # The field is written only by requests of the session itself, which
    #   are sent one by one, so it does not change between the read and
    #   the write below
    existing = _parse_session(await pool.hget(task_key, session_id))
    if existing is None:
        await _ensure_task_exists(project_name, task_id)
    elif existing.username != user.name:
        raise ForbiddenException("Session is owned by a different user")

    ttl = max(MIN_TTL, min(MAX_TTL, payload.ttl))
    now = datetime.now(timezone.utc).isoformat()
    opened_at = updated_at = now
    if existing is not None:
        opened_at = existing.opened_at
        if payload.heartbeat:
            updated_at = existing.updated_at

    session = TaskSessionModel(
        session_id=session_id,
        username=user.name,
        machine=payload.machine,
        site_id=payload.site_id,
        host_name=payload.host_name,
        workfile=payload.workfile,
        opened_at=opened_at,
        updated_at=updated_at,
    )
    data = session.dict(by_alias=True)
    data[EXPIRES_AT_KEY] = time.time() + ttl
    async with pool.pipeline(transaction=True) as pipe:
        pipe.hset(task_key, session_id, json_dumps(data))
        pipe.expire(task_key, REDIS_KEY_TTL)
        pipe.hgetall(task_key)
        _, _, payloads = await pipe.execute()

    return ClaimTaskResponseModel(sessions=_parse_sessions(payloads), ttl=ttl)


async def release_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    session_id: str = SessionID,
) -> EmptyResponse:
    """Unregister a session from a task.

    A session can be released by the user who did claim it or by
    a manager. Session that does not exist is ignored.
    """
    pool = await _get_redis_pool()
    task_key = _task_key(project_name, task_id)
    existing = _parse_session(await pool.hget(task_key, session_id))
    if (
        existing is not None
        and existing.username != user.name
        and not user.is_manager
    ):
        raise ForbiddenException("Session is owned by a different user")

    await pool.hdel(task_key, session_id)
    return EmptyResponse()


async def get_task_sessions(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
) -> TaskSessionsModel:
    """Get sessions working on a task."""
    return TaskSessionsModel(
        sessions=await _get_sessions(project_name, task_id)
    )


async def query_tasks_sessions(
    user: CurrentUser,
    project_name: ProjectName,
    payload: TasksQueryModel,
) -> TasksSessionsModel:
    """Get sessions working on multiple tasks."""
    task_ids = sorted(set(payload.task_ids))
    if not task_ids:
        return TasksSessionsModel()

    pool = await _get_redis_pool()
    async with pool.pipeline(transaction=False) as pipe:
        for task_id in task_ids:
            pipe.hgetall(_task_key(project_name, task_id))
        results = await pipe.execute()

    tasks = {}
    for task_id, payloads in zip(task_ids, results):
        sessions = _parse_sessions(payloads)
        if sessions:
            tasks[task_id] = sessions
    return TasksSessionsModel(tasks=tasks)


def register_task_usage_endpoints(addon: "BaseServerAddon") -> None:
    """Add task in-use endpoints to the addon."""
    base = "/projects/{project_name}/taskInUse"
    addon.add_endpoint(
        f"{base}/query",
        query_tasks_sessions,
        method="POST",
        name="query_tasks_in_use",
    )
    addon.add_endpoint(
        f"{base}/{{task_id}}",
        get_task_sessions,
        method="GET",
        name="get_task_in_use",
    )
    addon.add_endpoint(
        f"{base}/{{task_id}}/{{session_id}}",
        claim_task,
        method="PUT",
        name="claim_task_in_use",
    )
    addon.add_endpoint(
        f"{base}/{{task_id}}/{{session_id}}",
        release_task,
        method="DELETE",
        name="release_task_in_use",
    )
