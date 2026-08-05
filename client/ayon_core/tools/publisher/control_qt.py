from __future__ import annotations

import collections
from dataclasses import dataclass
import typing

from qtpy import QtCore

from ayon_core.pipeline.publish.logic import PublishIterAction

from .control import PublisherController

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.publish.logic import (
        PublishIterInfo,
        PluginType,
    )


class MainThreadItem:
    """Callback with args and kwargs."""

    def __init__(self, callback, *args, **kwargs):
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        self.process()

    def process(self):
        self.callback(*self.args, **self.kwargs)


class MainThreadProcess(QtCore.QObject):
    """Qt based main thread process executor.

    Has timer which controls each 50ms if there is new item to process.

    This approach gives ability to update UI meanwhile plugin is in progress.
    """

    count_timeout = 2

    def __init__(self):
        super().__init__()
        self._items_to_process = collections.deque()

        timer = QtCore.QTimer()
        timer.setInterval(0)

        timer.timeout.connect(self._execute)

        self._timer = timer

    def add_item(self, item):
        self._items_to_process.append(item)

    def _execute(self):
        if not self._items_to_process:
            return

        item = self._items_to_process.popleft()
        item.process()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def clear(self):
        self._items_to_process = collections.deque()
        self.stop()


@dataclass
class _IterData:
    """Store iteration data for a single publish process.

    Changes of the value do trigger an event (not handled by this class).

    """
    # Store the label of the current item being processed
    item_label: str = ""
    # Store the current plugin being processed
    plugin: PluginType | None = None
    # Store whether the publish process has been validated
    validated: bool = False


class QtPublisherController(PublisherController):
    def __init__(self, *args, **kwargs):
        self._main_thread_processor = MainThreadProcess()

        super().__init__(*args, **kwargs)

        self.register_event_callback(
            "publish.process.started", self._qt_on_publish_start
        )
        self.register_event_callback(
            "publish.process.stopped", self._qt_on_publish_stop
        )
        # Capture if '_next_publish_item_process' is in
        #   '_main_thread_processor' loop
        self._item_process_in_loop = False
        self._iter_data = _IterData()

    def reset(self):
        self._main_thread_processor.clear()
        self._item_process_in_loop = False
        self._iter_data = _IterData()
        super().reset()

    def _start_publish(self, stop_after_validation: bool) -> None:
        self._publish_model.set_publish_stop_after_validation(
            stop_after_validation
        )
        self._publish_model.start_publish(wait=False)
        # Make sure '_next_publish_item_process' is only once in
        #   the '_main_thread_processor' loop
        if not self._item_process_in_loop:
            self._process_main_thread_item(
                MainThreadItem(self._next_publish_item_process)
            )

    def _next_publish_item_process(self):
        if not self._publish_model.is_running():
            # This removes '_next_publish_item_process' from loop
            self._item_process_in_loop = False
            return

        self._item_process_in_loop = True
        self._process_main_thread_item(
            MainThreadItem(self._publish_model.process_next_iter)
        )

    def _process_main_thread_item(self, item):
        self._main_thread_processor.add_item(item)

    def _qt_on_publish_start(self):
        self._main_thread_processor.start()

    def _qt_on_publish_stop(self):
        self._process_main_thread_item(
            MainThreadItem(self._main_thread_processor.stop)
        )
