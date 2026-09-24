from __future__ import annotations

from typing import Any

from ayon_core.ipc_communication import IPCServer, RequestMessage

from .control import LoaderController


class IPCLoaderBackend(LoaderController):
    channel_name = "loader"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._ipc_server: IPCServer | None = None

    def register_ipc_handler(self, ipc_server: IPCServer) -> None:
        self._ipc_server = ipc_server
        ipc_server.register_handler(
            self.channel_name,
            self._channel_handler,
        )

    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        super().emit_event(topic, data, source)

        new_data = {}
        for key, value in data.items():
            if isinstance(value, set):
                value = list(value)
            new_data[key] = value

        self._ipc_server.trigger_method(
            self.channel_name,
            "emit_event",
            {"topic": topic, "data": new_data, "source": source},
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
            "trigger_action_item",
        ):
            self._execute_in_host_main_thread(func, **message.params)
            return None

        return func(**message.params)

    def _execute_in_host_main_thread(self, func, **kwargs) -> Any:
        """Execute a function in the main thread of DCC."""
        if hasattr(self._host, "execute_in_main_thread"):
            return self._host.execute_in_main_thread(func, **kwargs)
        raise RuntimeError(
            "Missing implementation of 'execute_in_main_thread' on host."
        )
