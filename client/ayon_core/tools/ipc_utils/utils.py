from __future__ import annotations

import collections
import platform
import typing

from qtpy import QtCore

from ayon_core.lib import Logger

if typing.TYPE_CHECKING:
    from typing import Any, Callable
    from ayon_core.ipc_api import ResponseMessage, RequestMessage, IPCClient

PLATFORM_NAME = platform.system().lower()


class CommunicationInfo:
    def __init__(self, client: IPCClient) -> None:
        self._client: IPCClient = client
        self._parent_process_is_alive: bool = True

    def send_request(
        self,
        channel: str,
        method: str,
        params: dict[str, Any] | None = None,
        callback: Callable[[ResponseMessage], None] | None = None,
    ) -> None:
        self._client.send_request(
            channel,
            method,
            params,
            callback,
        )

    def register_channel_handler(
        self, channel: str, handler: Callable[[RequestMessage], None]
    ) -> None:
        self._client.register_channel_handler(channel, handler)

    def is_parent_process_alive(self) -> bool:
        return self._parent_process_is_alive

    def on_parent_process_close(self) -> None:
        self._parent_process_is_alive = False


class WrappedCallbackItem:
    """Structure to store information about callback and args/kwargs for it.

    Item can be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    not_set = object()
    log = Logger.get_logger("WrappedCallbackItem")

    def __init__(self, callback, *args, **kwargs):
        self.done = False
        self.exception = self.not_set
        self.result = self.not_set
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

    def __call__(self):
        self.execute()

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        if self.done:
            self.log.warning("- item is already processed")
            return

        try:
            result = self._callback(*self._args, **self._kwargs)
            self.result = result

        except Exception as exc:
            self.exception = exc

        finally:
            self.done = True


def execute_in_main_thread(callback, *args, **kwargs):
    if isinstance(callback, WrappedCallbackItem):
        item = callback
    else:
        item = WrappedCallbackItem(callback, *args, **kwargs)

    _MainThreadHelper.queue.append(item)


def _process_main_thread_queue():
    """Process all items in the queue.

    Method must be called from main thread. All items in the queue are
    executed and removed from the queue.
    """
    for _ in range(len(_MainThreadHelper.queue)):
        item = _MainThreadHelper.queue.popleft()
        item.execute()


class _MainThreadHelper:
    queue = collections.deque()
    timer = QtCore.QTimer()
    timer.setInterval(10)
    timer.timeout.connect(_process_main_thread_queue)


def start_main_thread_helper():
    """Start main thread helper.

    Method must be called from main thread. Start timer which will process
    queue of items to be executed in main thread.
    """
    _MainThreadHelper.timer.start()
