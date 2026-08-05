from __future__ import annotations

from abc import abstractmethod
from typing import Any

from ayon_core.ipc_communication import IPCServer, RequestMessage

from .control import PublisherController


class IPCPublisherBackend(PublisherController):
    channel_name = "publisher"

    def __init__(self, host=None) -> None:
        super().__init__(host=host)

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

        self._ipc_server.trigger_method(
            self.channel_name,
            "emit_event",
            {"topic": topic, "data": data, "source": source},
        )

        super().emit_event(topic, data, source)

    def _channel_handler(
        self, ipc_server: IPCServer, message: RequestMessage
    ) -> Any:
        """Handle IPC messages for workfiles."""
        method_name = message.method
        if message.method == "show":
            ipc_server.trigger_method(
                self.channel_name,
                "show",
                message.params,
            )
            return None

        func = getattr(self, method_name)

        if method_name in (
            "save_changes",
            "create",
            "trigger_convertor_items",
        ):
            return self._execute_in_host_main_thread(func, **message.params)

        if method_name in (
            "set_instances_context_info",
            "set_instances_active_state",
            "set_instances_create_attr_values",
            "revert_instances_create_attr_values",
            "set_instances_publish_attr_values",
            "revert_instances_publish_attr_values",
            "trigger_pre_create_button_callback",
            "trigger_create_button_callback",
            "trigger_publish_button_callback",
            "remove_instances",
            "publish",
            "validate",
            "stop_publish",
            "run_action",
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

    def _start_publish(self, up_validation: bool) -> None:
        self._publish_model.set_publish_up_validation(up_validation)
        self._publish_model.start_publish(wait=False)
        self._execute_in_host_main_thread(self._next_process)

    def _next_process(self) -> None:
        if self._publish_model.is_running():
            func = self._publish_model.get_next_process_func()
            func()
            self._execute_in_host_main_thread(self._next_process)
