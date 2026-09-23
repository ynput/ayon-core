"""Standard way to load data for Qt views without blocking the UI.

UI data loading standard
========================

Every Qt model which shows data coming from a controller follows these
rules. They keep the UI responsive no matter how slow the server, the
disk or the amount of data is.

1. **Never call blocking controller getters on the UI thread in reaction
   to user interaction.** Selection changes, clicks and page switches only
   ask for data using :class:`AsyncLoader`.
2. **Split every refresh into 'fetch' and 'apply'.** ``fetch`` runs in a
   worker thread of the shared :func:`get_task_queue` and does all I/O:
   server requests, filesystem access, downloads of icon content
   (see ``ayon_core.tools.utils.prefetch_qt_icons``) and any heavy pure
   Python preparation. ``apply`` runs on the UI thread and only touches Qt
   objects. ``fetch`` must not touch the model or widgets.
3. **Latest request wins.** A new request cancels the previous one and
   results of outdated requests are never applied, so fast clicking
   through items never shows data for the wrong selection.
4. **Keep 'apply' cheap for big data.** Build ``QStandardItem`` trees
   detached in ``fetch`` (items without a model are plain C++ objects, safe
   to create in a worker thread) and attach them in one model reset, or
   apply a diff to keep the view state. Use real items for every column
   instead of Python ``data``/``flags`` overrides, and plain ``int`` roles
   in hot loops (PySide6 enum access is slow).
5. **Show loading state.** Views show a skeleton loader while loading and
   there is nothing to show yet (``AYTreeView.set_loading``), driven by
   :attr:`AsyncLoader.loading_changed`. Content for a previous selection
   must not stay clickable while it does not match the current selection.
6. **Events emitted from worker threads are delivered on the UI thread.**
   Controllers used by async models must make ``emit_event`` thread safe,
   e.g. by passing the emit to ``ayon_core.tools.utils.run_in_main_thread``
   when called outside of the UI thread.

Example:
    ```python
    class TasksModel(QtGui.QStandardItemModel):
        def __init__(self, controller):
            super().__init__()
            self._controller = controller
            self._loader = AsyncLoader("tasks", priority=1, parent=self)

        def set_folder(self, project_name, folder_id):
            self._loader.request(
                lambda: self._controller.get_task_items(
                    project_name, folder_id
                ),
                self._fill,
            )

        def _fill(self, task_items):
            ...  # UI thread, Qt objects only
    ```
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Optional

from qtpy.QtCore import QObject, Signal

from .task_queue import AsyncTask, get_task_queue

log = logging.getLogger(__name__)


class _Failure:
    """Marker result of a fetch which raised an exception."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.traceback = traceback.format_exc()


class AsyncLoader(QObject):
    """Load data in a worker thread and apply it on the UI thread.

    Only the latest request is applied. A new request cancels the previous
    one, if it did not start yet it will not run at all.

    Args:
        name: Name used for tasks in the queue and in logs.
        priority: Priority in the shared task queue, lower is sooner.
        parent: Parent object.
    """

    #: Emitted when the loader starts or stops waiting for a result.
    loading_changed = Signal(bool)

    def __init__(
        self,
        name: str,
        priority: int = 2,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._priority = priority
        self._generation = 0
        self._task: Optional[AsyncTask] = None
        self._is_loading = False

    def is_loading(self) -> bool:
        """Is a request waiting for its result."""
        return self._is_loading

    def request(
        self,
        fetch: Callable[[], Any],
        apply: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        """Request new data.

        Args:
            fetch: Called in a worker thread, returns data for 'apply'.
                Must not touch Qt models or widgets.
            apply: Called on the UI thread with the result of 'fetch'.
            on_error: Called on the UI thread when 'fetch' raised an
                exception. The exception is logged either way.
        """
        self._cancel_task()
        generation = self._generation

        def _fetch():
            try:
                return fetch()
            except Exception as exc:
                return _Failure(exc)

        task = AsyncTask(
            name=self._name,
            function=_fetch,
            callback=lambda result: self._on_result(
                generation, result, apply, on_error
            ),
            priority=self._priority,
            context_id=f"{self._name}_{id(self)}",
            cancellable=True,
        )
        self._task = task
        self._set_loading(True)
        get_task_queue().enqueue(task)

    def cancel(self) -> None:
        """Cancel the running request, its result is never applied."""
        self._cancel_task()
        self._set_loading(False)

    def _cancel_task(self) -> None:
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _on_result(
        self,
        generation: int,
        result: Any,
        apply: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]],
    ) -> None:
        if generation != self._generation:
            return
        self._task = None
        try:
            if isinstance(result, _Failure):
                log.error(
                    "Failed to load '%s'\n%s", self._name, result.traceback
                )
                if on_error is not None:
                    on_error(result.exc)
            else:
                apply(result)
        finally:
            # 'apply' may have started a new request
            if self._task is None:
                self._set_loading(False)

    def _set_loading(self, is_loading: bool) -> None:
        if self._is_loading == is_loading:
            return
        self._is_loading = is_loading
        self.loading_changed.emit(is_loading)
