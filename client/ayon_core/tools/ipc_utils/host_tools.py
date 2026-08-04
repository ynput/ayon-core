from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess
import time
import typing
from typing import Any

from ayon_core.lib import (
    get_ayon_launcher_args,
    get_launcher_storage_dir,
    emit_event,
)
from ayon_core.pipeline import registered_host

from ayon_core.ipc_api import IPCServer, Message

from ayon_core.tools.loader.ipc_backend_control import IPCLoaderBackend
from ayon_core.tools.publisher.ipc_backend_control import IPCPublisherBackend
from ayon_core.tools.workfiles.ipc_backend_control import IPCWorkfilesBackend

if typing.TYPE_CHECKING:
    from typing import Literal

    PublisherTab = Literal["create", "publish"] | None


CURRENT_DIR = Path(__file__).parent
SRIPT_PATH = CURRENT_DIR / "ui_process.py"

logger = logging.getLogger(__name__)


@dataclass
class _ToolBackends:
    loader_backend: IPCLoaderBackend
    publisher_backend: IPCPublisherBackend
    workfiles_backend: IPCWorkfilesBackend


# IPC and external UI process management
class _IPCConnection:
    server: IPCServer | None = None
    ui_process: subprocess.Popen | None = None
    ui_backends: _ToolBackends | None = None


def _launch_ui_process(
    ipc_host: str, ipc_port: int, session_token: str
) -> subprocess.Popen:
    env = os.environ.copy()
    env["AYON_IPC_PID"] = str(os.getpid())
    env["AYON_IPC_HOST"] = ipc_host
    env["AYON_IPC_PORT"] = str(ipc_port)
    env["AYON_IPC_TOKEN"] = session_token
    launch_args = get_ayon_launcher_args(
        str(SRIPT_PATH), "--skip-bootstrap"
    )
    logger.info("Launching external UI host with: %s", launch_args)
    # TODO find a better way how to add current dependency packages to
    # PYTHONPATH for the external UI process. This is needed because of
    # '--skip-bootstrap' argument.
    dp_dir = Path(get_launcher_storage_dir("dependency_packages"))
    runtime_dir = None
    python_path = []
    for path in os.getenv("PYTHONPATH", "").split(os.pathsep):
        if not path:
            continue
        python_path.append(path)
        path_obj = Path(path).resolve()
        if path_obj.is_relative_to(dp_dir):
            relative_path = path_obj.relative_to(dp_dir)
            dp_name = relative_path.parts[0]
            runtime_dir = dp_dir / dp_name / "runtime"
            if runtime_dir.exists():
                break

    if runtime_dir:
        python_path.insert(0, str(runtime_dir))
        env["PYTHONPATH"] = os.pathsep.join(python_path)

    # NOTE This is temporary solution which does show the process terminal
    # return subprocess.Popen(
    #     launch_args,
    #     env=env,
    #     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    # )
    return subprocess.Popen(
        launch_args,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_ipc_server_healthy() -> bool:
    """Return whether IPC server instance is alive and listening."""
    server = _IPCConnection.server
    if server is None:
        return False

    thread = server.server_thread
    if not server.running or thread is None or not thread.is_alive():
        return False

    return server.server_socket is not None


def _init_ipc_server():
    """Initialize the IPC server for external UI communication."""
    if _is_ipc_server_healthy():
        return _IPCConnection.server

    # Recover from stale server objects that are no longer listening.
    if _IPCConnection.server is not None:
        logger.warning("IPC server was stale; recreating it")
        try:
            _IPCConnection.server.stop()
        except Exception:
            logger.debug("Failed stopping stale IPC server", exc_info=True)
        _IPCConnection.server = None

    try:

        server = IPCServer()
        port = server.start()
        logger.info("IPC server listening on 127.0.0.1:%s", port)

        # Register handlers for common operations
        _register_ipc_handlers(server)
        _IPCConnection.server = server

        _ensure_external_ui_process()

        return _IPCConnection.server

    except Exception as e:
        logger.error(f"Failed to initialize IPC server: {e}", exc_info=True)
        _IPCConnection.server = None
        return None


def _ensure_external_ui_process():
    """Ensure external UI process is running when external UI mode is enabled."""
    if not _is_ipc_server_healthy():
        _init_ipc_server()

    if _IPCConnection.server is None:
        return

    if _IPCConnection.ui_process and _IPCConnection.ui_process.poll() is None:
        return

    token = _IPCConnection.server.get_session_token()
    _IPCConnection.ui_process = _launch_ui_process(
        ipc_host="127.0.0.1",
        ipc_port=_IPCConnection.server.port,
        session_token=token,
    )
    logger.info(
        "External UI process launched (PID: %s)",
        _IPCConnection.ui_process.pid
    )


def _register_ipc_handlers(server: IPCServer):
    """Register request handlers for IPC server."""
    host = registered_host()
    ui_backends = _ToolBackends(
        loader_backend=IPCLoaderBackend(host),
        publisher_backend=IPCPublisherBackend(host),
        workfiles_backend=IPCWorkfilesBackend(host),
    )
    ui_backends.loader_backend.register_ipc_handler(server)
    ui_backends.publisher_backend.register_ipc_handler(server)
    ui_backends.workfiles_backend.register_ipc_handler(server)

    _IPCConnection.ui_backends = ui_backends

    # TODO allow to register custom handlers
    # if hasattr(host, "register_ipc_handlers"):
    #     host.register_ipc_handlers(server)
    #
    # emit_event(
    #     "ipc.handlers.registered",
    #     {
    #         "host": host,
    #         "server": server,
    #     }
    # )

def _shutdown_ipc_server() -> None:
    """Shutdown the IPC server and external UI process."""
    if _IPCConnection.server:
        try:
            _IPCConnection.server.stop()
        except Exception as e:
            logger.error(f"Error stopping IPC server: {e}")
        _IPCConnection.server = None

    if _IPCConnection.ui_process:
        try:
            _IPCConnection.ui_process.terminate()
            _IPCConnection.ui_process.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error terminating UI process: {e}")
        _IPCConnection.ui_process = None


class IPCHostTools:
    @classmethod
    def init(cls):
        """Initialize the IPC server and external process."""
        _init_ipc_server()

    @classmethod
    def process_requests(cls):
        """Process IPC requests send pending requests to client."""
        if _IPCConnection.server is None:
            return

        _IPCConnection.server.process_requests()

    @classmethod
    def execute(
        cls,
        channel: str,
        method_name: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        _ensure_external_ui_process()

        server = _IPCConnection.server
        if not server:
            return False

        server.trigger_method(
            channel,
            method_name,
            params,
        )
        return True

    @classmethod
    def shutdown(cls):
        _shutdown_ipc_server()

    @classmethod
    def show_loader(cls) -> None:
        _ensure_external_ui_process()
        cls.execute("loader", "show")

    @classmethod
    def show_publisher(cls, tab: PublisherTab = None) -> None:
        _ensure_external_ui_process()
        cls.execute("publisher", "show", {"tab": tab})

    @classmethod
    def show_workfiles(cls) -> None:
        _ensure_external_ui_process()
        cls.execute("workfiles", "show")

