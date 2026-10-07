"""Task in-use sessions (advisory task locking).

A session of a user working on a task is stored in Redis with a time to
live. The session must be refreshed (heartbeat) to stay alive, so sessions
of crashed applications expire on their own.

Nothing is stored on the task entity, so the sessions do not change the
task, do not create events and a user does not need permissions to write
to the task. Any user with access to the project can use the endpoints.

Redis keys:
    Each session has its own key with the time to live. Ids of sessions of
    a task are stored in a set, which is used to find the sessions without
    scanning of all keys. Ids of expired sessions are removed from the set
    when the sessions of the task are listed.
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import Path

from ayon_server.api.dependencies import CurrentUser, ProjectName, TaskID
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import BadRequestException, ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel
from ayon_server.utils import json_loads

if TYPE_CHECKING:
    from ayon_server.addons import BaseServerAddon

REDIS_NAMESPACE = "core-task-in-use"
REDIS_INDEX_NAMESPACE = "core-task-in-use-index"

DEFAULT_TTL = 5 * 60
MIN_TTL = 30
MAX_TTL = 60 * 60
MAX_TASKS_PER_QUERY = 500

SESSION_ID_REGEX = r"^[a-zA-Z0-9_-]{1,64}$"


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


def _session_key(project_name: str, task_id: str, session_id: str) -> str:
    return f"{project_name}-{task_id}-{session_id}"


def _full_key(namespace: str, key: str) -> str:
    """Key as is stored by 'Redis' helper."""
    return f"{Redis.prefix}{namespace}-{key}"


def _index_key(project_name: str, task_id: str) -> str:
    return _full_key(REDIS_INDEX_NAMESPACE, f"{project_name}-{task_id}")


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


async def _get_redis_pool():
    if not Redis.connected:
        await Redis.connect()
    return Redis.redis_pool


async def _get_sessions(
    project_name: str, task_id: str
) -> list[TaskSessionModel]:
    """Sessions of a task that did not expire."""
    pool = await _get_redis_pool()
    index_key = _index_key(project_name, task_id)
    session_ids = sorted(
        _decode(session_id)
        for session_id in await pool.smembers(index_key)
    )
    if not session_ids:
        return []

    payloads = await pool.mget([
        _full_key(
            REDIS_NAMESPACE,
            _session_key(project_name, task_id, session_id),
        )
        for session_id in session_ids
    ])
    sessions = []
    expired_ids = []
    for session_id, payload in zip(session_ids, payloads):
        if payload is None:
            expired_ids.append(session_id)
            continue
        try:
            sessions.append(TaskSessionModel(**json_loads(payload)))
        except Exception:
            expired_ids.append(session_id)

    if expired_ids:
        await pool.srem(index_key, *expired_ids)

    sessions.sort(key=lambda session: session.opened_at)
    return sessions


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
    key = _session_key(project_name, task_id, session_id)
    existing = await Redis.get_json(REDIS_NAMESPACE, key)
    if not isinstance(existing, dict):
        existing = None

    if existing is None:
        await _ensure_task_exists(project_name, task_id)
    elif existing.get("username") != user.name:
        raise ForbiddenException("Session is owned by a different user")

    ttl = max(MIN_TTL, min(MAX_TTL, payload.ttl))
    now = datetime.now(timezone.utc).isoformat()
    opened_at = updated_at = now
    if existing is not None:
        opened_at = existing.get("openedAt") or now
        if payload.heartbeat:
            updated_at = existing.get("updatedAt") or now

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
    await Redis.set_json(
        REDIS_NAMESPACE, key, session.dict(by_alias=True), ttl=ttl
    )

    pool = await _get_redis_pool()
    index_key = _index_key(project_name, task_id)
    await pool.sadd(index_key, session_id)
    # The set must live at least as long as any of the sessions
    await pool.expire(index_key, MAX_TTL)

    return ClaimTaskResponseModel(
        sessions=await _get_sessions(project_name, task_id),
        ttl=ttl,
    )


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
    key = _session_key(project_name, task_id, session_id)
    existing = await Redis.get_json(REDIS_NAMESPACE, key)
    if (
        isinstance(existing, dict)
        and existing.get("username") != user.name
        and not user.is_manager
    ):
        raise ForbiddenException("Session is owned by a different user")

    await Redis.delete(REDIS_NAMESPACE, key)
    pool = await _get_redis_pool()
    await pool.srem(_index_key(project_name, task_id), session_id)
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
    tasks = {}
    for task_id in set(payload.task_ids):
        sessions = await _get_sessions(project_name, task_id)
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
