"""Run AYON Qt tools in an external process and control them via IPC events."""

import os
import sys
import logging
import time

import psutil

from ayon_core.ipc_communication import IPCClient
from ayon_core.tools.utils import get_ayon_qt_app
from ayon_core.tools.loader.ipc_frontend_control import IPCLoaderFrontend
from ayon_core.tools.workfiles.ipc_frontend_control import (
    IPCWorkfilesFrontend
)
from ayon_core.tools.publisher.ipc_frontend_control import (
    IPCPublisherFrontend
)
from ayon_core.tools.ipc_utils.utils import (
    start_main_thread_helper,
    execute_in_main_thread,
    CommunicationInfo,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class IPCProcess:
    def __init__(
        self,
        pid: int | None = None,
        ipc_host: str | None = None,
        ipc_port: int | None = None,
        session_token: str | None = None,
    ) -> None:
        if pid is None:
            pid = int(os.environ["AYON_IPC_PID"])

        if ipc_host is None:
            ipc_host = os.environ["AYON_IPC_HOST"]

        if ipc_port is None:
            ipc_port = int(os.environ["AYON_IPC_PORT"])

        if session_token is None:
            session_token = os.environ["AYON_IPC_TOKEN"]

        if not ipc_port or not session_token:
            raise ValueError("Missing IPC bootstrap env vars")

        self.pid: int = pid
        self.ipc_host: str = ipc_host
        self.ipc_port: int = ipc_port
        self.session_token: str = session_token

        self.ipc = IPCClient(
            host=ipc_host,
            port=ipc_port,
            session_token=session_token,
        )
        self.com_info = CommunicationInfo(self.ipc)

        self.app = get_ayon_qt_app()

        self.loader_handler = IPCLoaderFrontend(self.com_info)
        self.publisher_handler = IPCPublisherFrontend(self.com_info)
        self.workfiles_handler = IPCWorkfilesFrontend(self.com_info)

        self.register_handlers()

        self._connect()

    def register_handlers(self) -> None:
        """Register custom handlers for IPC events.

        Override this method in subclasses to add custom behavior.
        """
        pass

    def start_app(self) -> None:
        """Call this method to start the app and enter the event loop."""
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(self._on_close)
        start_main_thread_helper()
        execute_in_main_thread(self._tick)
        sys.exit(self.app.exec())

    def _connect(self) -> None:
        """Establish a connection to the parent IPC server."""
        # Give parent-side server a short startup window before hard failure.
        deadline = time.time() + 10.0
        while not self.ipc.connect() and time.time() < deadline:
            time.sleep(0.5)

        if not self.ipc.is_connected():
            raise RuntimeError("Could not connect to parent IPC server")

    def _on_close(self) -> None:
        if self.ipc.is_connected():
            self.ipc.disconnect()
        self.app.exit(0)

    def _tick(self) -> None:
        # Keep the process alive and attempt reconnection.
        if self.ipc.is_connected():
            execute_in_main_thread(self._tick)
            return

        if psutil.pid_exists(self.pid):
            execute_in_main_thread(self._tick)
            self.ipc.reconnect_with_backoff()
            return

        logger.error("Parent process has exited")
        if self.ipc.is_connected():
            self.ipc.disconnect()
        self.app.exit(0)
