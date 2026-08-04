from __future__ import annotations

from abc import abstractmethod
from typing import Any

from ayon_core.ipc_api import IPCServer, RequestMessage

from .control import BaseWorkfileController


class IPCWorkfilesBackend(BaseWorkfileController):
    channel_name = "workfiles"

    @abstractmethod
    def _execute_in_host_main_thread(self, func, **kwargs) -> Any:
        """Execute a function in the main thread of DCC."""
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._ipc_server: IPCServer | None = None

    def register_ipc_handler(self, ipc_server: IPCServer):
        self._ipc_server = ipc_server
        ipc_server.register_handler(
            self.channel_name,
            self._channel_handler,
        )

    # --- Custom handling of events ---
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)
        self._ipc_server.trigger_method(
            self.channel_name,
            "emit_event",
            {"topic": topic, "data": data, "source": source},
        )

    def _channel_handler(
        self, ipc_server: IPCServer, message: RequestMessage
    ):
        """Handle IPC messages for workfiles."""
        method_name = message.method
        if message.method == "show":
            ipc_server.trigger_method(
                self.channel_name,
                "show",
            )
            return None

        func = getattr(self, method_name)
        if method_name in (
            "open_workfile",
            "save_as_workfile",
            "copy_workfile_representation",
            "duplicate_workfile",
        ):
            return self._execute_in_host_main_thread(func, **message.params)

        return func(**message.params)
