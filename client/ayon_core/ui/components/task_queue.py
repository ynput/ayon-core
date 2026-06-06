"""Priority-based async task queue backed by a dispatch QThread + worker pool.

This module provides a generic priority-based task queue system.  A single
*dispatch* ``QThread`` dequeues tasks from a ``PriorityQueue`` and submits
them to a ``ThreadPoolExecutor``  (default: 4 workers) so that independent
fetches — for instance all children of simultaneously-expanded tree nodes —
run **in parallel** rather than serially.

Key optimisations vs. the original single-worker design:

* **No polling sleep** - the dispatch loop blocks on a ``threading.Event``
  that is set by :meth:`AsyncTaskQueue.enqueue` the instant a new task
  arrives, so there is zero idle wait between tree-expansion waves.
* **Parallel execution** - up to ``num_workers`` fetch tasks run at the
  same time, halving the effective latency when expanding N sibling nodes
  from O(N × round-trip) to O(round-trip / num_workers × N).

Each task carries an optional ``context_id`` label. External components can
call :meth:`AsyncTaskQueue.clear_context_tasks` to remove all pending tasks
for a given context when the associated state becomes stale (e.g. a selection
change).  Multiple distinct context IDs can coexist in the queue at the same
time.
"""

from __future__ import annotations

import concurrent.futures
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, Callable

from qtpy.QtCore import (
    Qt,
    QThread,
    QTimer,
    Signal,  # type: ignore
    Slot,  # type: ignore
)

log = logging.getLogger(__name__)

# Number of parallel pool workers created by default.
_DEFAULT_NUM_WORKERS: int = 4


@dataclass
@total_ordering
class AsyncTask:
    """Represents a task to be executed by the async task queue.

    This class holds all the information needed to execute an asynchronous
    operation, including the work function, callback, priority, and context
    tracking for cancellation support.

    Attributes:
        name: Descriptive name for the task (e.g., "fetch_activity_data").
        function: Callable that performs the work.
        callback: Function to call with the result when task completes.
        priority: Priority level (lower numbers = higher priority).
            0 = Critical (UI blocking operations)
            1 = High (User-initiated operations)
            5 = Normal (Background fetches)
            10 = Low (Prefetching)
        context_id: Optional label grouping related tasks. Pass the same
            id to :meth:`AsyncTaskQueue.clear_context_tasks` to remove all
            pending tasks for that group at once.
        cancellable: If True, the task can be removed by
            :meth:`AsyncTaskQueue.clear_context_tasks`.

    Example:
        task = AsyncTask(
            name="fetch_activities",
            function=lambda: fetch_data(context),
            callback=on_data_ready,
            priority=1,
            context_id="project:item_id",
            cancellable=True
        )
    """

    name: str
    function: Callable[[], Any]
    callback: Callable[[Any], None]
    priority: int = 5
    context_id: str = ""
    cancellable: bool = True

    # Internal state
    _counter: int = field(default=0, init=False, compare=True)
    _cancelled: bool = field(default=False, init=False, repr=False)

    def cancel(self) -> None:
        """Mark this task as cancelled.

        Only affects the task if cancellable is True.
        """
        if self.cancellable:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        """Check if this task has been cancelled.

        Returns:
            True if the task has been cancelled, False otherwise.
        """
        return self._cancelled

    def __lt__(self, other: AsyncTask) -> bool:
        """Compare tasks by priority, then by counter for FIFO ordering.

        Args:
            other: Another AsyncTask to compare with.

        Returns:
            True if this task should be processed before the other task.
        """
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._counter < other._counter

    def __eq__(self, other: object) -> bool:
        """Check equality based on priority and counter.

        Args:
            other: Object to compare with.

        Returns:
            True if tasks have equal priority and counter.
        """
        if not isinstance(other, AsyncTask):
            return NotImplemented
        return (self.priority, self._counter) == (
            other.priority,
            other._counter,
        )


class AsyncTaskQueue(QThread):
    """Dispatch thread + pool that processes async tasks from a priority queue.

    A single ``QThread`` (the *dispatch loop*) continuously dequeues the
    highest-priority task and submits it to an internal
    ``ThreadPoolExecutor`` so that multiple tasks can execute in parallel.

    This removes two performance bottlenecks that made multi-level tree
    expansion slow in the original single-worker design:

    1. **No idle polling** - instead of sleeping 50 ms when the queue is
       empty, the dispatch loop blocks on a ``threading.Event`` that
       :meth:`enqueue` sets immediately, so there is zero dead time between
       a tree-level's results arriving on the main thread, new
       ``fetchMore`` calls being enqueued, and those fetches starting.

    2. **Parallel execution** - up to ``num_workers`` fetches run
       concurrently, so expanding a folder with N children takes
       ``ceil(N / num_workers)`` round-trips instead of N.

    Signals:
        task_completed: Emitted when a task finishes (task_name, result).
        task_failed: Emitted when a task raises exception (task_name, err).
        task_cancelled: Emitted when task is cancelled (task_name, ctx_id).
        queue_empty: Emitted when all tasks are processed.

    Multiple :attr:`~AsyncTask.context_id` values can coexist in the queue.
    Call :meth:`clear_context_tasks` to remove all pending tasks for a given
    context when external state changes make them irrelevant.

    Args:
        num_workers: Number of parallel pool workers (default 4).
        parent: Optional parent QObject.

    Example:
        queue = AsyncTaskQueue()
        queue.task_completed.connect(handle_completion)
        queue.start()

        task = AsyncTask(...)
        queue.enqueue(task)

        # When the context is no longer relevant:
        queue.clear_context_tasks(context_id)

        # Later...
        queue.stop()
    """

    # Qt Signals
    task_completed = Signal(str, object)  # (task_name, result)
    task_failed = Signal(str, str)  # (task_name, error_message)
    task_cancelled = Signal(str, str)  # (task_name, context_id)
    task_enqueued = Signal(str, int)  # (task_name, priority)
    task_started = Signal(str)  # (task_name)
    queue_empty = Signal()
    # No-arg ping signal: tells the main thread to drain _callback_queue.
    # Never passes Python objects through Qt's cross-thread signal system.
    invoke_callback = Signal()

    def __init__(
        self,
        parent: Any = None,
        num_workers: int = _DEFAULT_NUM_WORKERS,
    ) -> None:
        """Initialise the dispatch thread and pool.

        Args:
            num_workers: Number of parallel pool workers. Defaults to
                :data:`_DEFAULT_NUM_WORKERS` (4).
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._task_queue: queue.PriorityQueue = queue.PriorityQueue()
        # Thread-safe Python queue for ferrying (callback, result) pairs.
        # Using Python's own ref-counting rather than Qt's marshaling avoids
        # PySide6 issues with Python-callable arguments in QueuedConnection.
        self._callback_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._running: bool = False
        self._paused: threading.Event = threading.Event()
        self._paused.set()  # Start unpaused
        self._task_counter: int = 0
        self._counter_lock: threading.Lock = threading.Lock()
        # Serialises drain-and-rebuild operations in _filter_queue so that
        # the worker thread cannot dequeue a task between two get_nowait()
        # calls while the main thread is rebuilding the queue.
        self._queue_lock: threading.Lock = threading.Lock()
        # Set by enqueue() to wake the dispatch loop immediately instead of
        # waiting for the polling timeout.
        self._task_available: threading.Event = threading.Event()
        self._num_workers: int = num_workers
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

        # Connect the no-arg ping to the drain slot on the main thread.
        self.invoke_callback.connect(
            self._drain_callback_queue,
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def _drain_callback_queue(self) -> None:
        """Process a small batch of pending callbacks, then yield.

        Called via a QueuedConnection so it always runs on the Qt main
        thread regardless of which thread emitted invoke_callback.

        Up to ``_CALLBACK_BATCH_LIMIT`` callbacks are executed per
        invocation, subject to a ``_CALLBACK_TIME_BUDGET_MS`` millisecond
        wall-clock budget.  Stopping after each batch allows the event
        loop to process paint events, keeping the UI responsive when many
        async tasks complete simultaneously (e.g. auto-expand with
        many folders).

        If callbacks remain after the budget is exhausted, a 1 ms
        single-shot timer re-schedules this method so that paint events
        can be processed before the next batch.
        """
        _BATCH_LIMIT = 5
        _TIME_BUDGET_MS = 8

        t0 = time.monotonic()
        for _ in range(_BATCH_LIMIT):
            try:
                callback, result = self._callback_queue.get_nowait()
            except queue.Empty:
                return
            try:
                callback(result)
            except Exception as e:
                log.exception("Callback execution failed: %s", e)
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms >= _TIME_BUDGET_MS:
                break

        # If more items remain, schedule the next drain after yielding
        # to the event loop so paint events can be processed.
        if not self._callback_queue.empty():
            QTimer.singleShot(1, self._drain_callback_queue)

    def run(self) -> None:
        """Dispatch loop - runs in the QThread context.

        Dequeues the highest-priority pending task and submits it to the
        thread pool.  Blocks on ``_task_available`` when the queue is empty
        so it wakes the instant :meth:`enqueue` adds a new task, eliminating
        the 50 ms polling delay of the previous single-worker design.
        """
        self._running = True
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._num_workers,
            thread_name_prefix="ayon_task_worker",
        )
        log.debug(
            "Task queue dispatch loop started (num_workers=%d)",
            self._num_workers,
        )

        try:
            while self._running:
                # Wait if paused
                self._paused.wait()

                try:
                    # Acquire the queue lock before dequeuing so that
                    # _filter_queue drain-and-rebuild on the main thread is
                    # atomic with respect to this get() call.
                    with self._queue_lock:
                        try:
                            priority, task = self._task_queue.get_nowait()
                        except queue.Empty:
                            task = None

                    if task is None:
                        # Block until a new task is enqueued (enqueue() sets
                        # _task_available) or the 0.5 s safety timeout fires.
                        # This replaces the original time.sleep(0.05) busy-
                        # poll, eliminating idle dead-time between expansion
                        # waves without wasting CPU.
                        self._task_available.wait(timeout=0.5)
                        self._task_available.clear()
                        continue

                    if task.is_cancelled():
                        log.debug("Skipping cancelled task: %s", task.name)
                        self.task_cancelled.emit(task.name, task.context_id)
                        if self._task_queue.empty():
                            self.queue_empty.emit()
                        continue

                    log.debug(
                        "Submitting task to pool: %s (context=%s)",
                        task.name,
                        task.context_id,
                    )
                    self._executor.submit(self._run_task_in_pool, task)

                    if self._task_queue.empty():
                        self.queue_empty.emit()

                except Exception as e:
                    log.exception("Unexpected error in dispatch loop: %s", e)
        finally:
            # cancel_futures=True (Python ≥ 3.9) drops queued-but-not-
            # started futures; already-running ones are awaited.
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

        log.debug("Task queue dispatch loop stopped")

    def _run_task_in_pool(self, task: AsyncTask) -> None:
        """Execute a single task inside a pool worker thread.

        Results are delivered back to the main thread via
        :meth:`_invoke_callback_safely`.

        Args:
            task: The task to execute.
        """
        # Re-check cancellation: the task may have been cancelled while
        # waiting in the executor's internal work queue.
        if task.is_cancelled():
            log.debug("Skipping cancelled task (pool): %s", task.name)
            return

        log.debug(
            "Processing task: %s (context=%s)", task.name, task.context_id
        )

        try:
            self.task_started.emit(task.name)
        except Exception:
            log.debug(
                "Failed to emit task_started for %s.", task.name, exc_info=True
            )

        try:
            result = task.function()

            # Double-check cancellation after execution.
            if task.is_cancelled():
                log.debug(
                    "Task %s completed but was cancelled, discarding result",
                    task.name,
                )
                return

            if task.callback:
                self._invoke_callback_safely(task.callback, result, task.name)

            try:
                self.task_completed.emit(task.name, result)
            except Exception:
                log.debug(
                    "Failed to emit task_completed for %s.",
                    task.name,
                    exc_info=True,
                )

            log.debug("Task completed successfully: %s", task.name)

        except Exception as e:
            log.exception("Task %s failed: %s", task.name, e)

            if task.callback:
                self._invoke_callback_safely(task.callback, None, task.name)

            try:
                self.task_failed.emit(task.name, str(e))
            except Exception:
                log.debug(
                    "Failed to emit task_failed for %s.",
                    task.name,
                    exc_info=True,
                )

    def _invoke_callback_safely(
        self, callback: Callable, result: Any, task_name: str
    ) -> None:
        """Invoke callback safely with unified error handling.

        Pushes (callback, result) onto a Python SimpleQueue so that
        Python callables never travel through Qt's cross-thread
        signal marshaling (which is unreliable for arbitrary callables
        in PySide6).  A no-arg ping signal then wakes the main thread.

        Args:
            callback: The callback function to invoke.
            result: The result to pass to the callback.
            task_name: Name of the task (for logging).
        """
        try:
            self._callback_queue.put_nowait((callback, result))
            self.invoke_callback.emit()
        except Exception as e:
            log.exception(
                "Error invoking callback for %s: %s",
                task_name,
                e,
            )

    def enqueue(self, task: AsyncTask) -> None:
        """Add a task to the queue (thread-safe).

        Assigns a monotonically increasing counter to the task to ensure
        FIFO ordering within the same priority level.  Sets
        ``_task_available`` so the dispatch loop wakes immediately instead
        of waiting for its polling timeout.

        Args:
            task: The task to enqueue.
        """
        # Assign a counter value for FIFO ordering within priority
        with self._counter_lock:
            task._counter = self._task_counter
            self._task_counter += 1

        # Add to priority queue
        self._task_queue.put((task.priority, task))
        # Notify observers that a task has been enqueued.
        try:
            self.task_enqueued.emit(task.name, task.priority)
        except Exception:
            log.debug(
                "Failed to emit task_enqueued for %s.",
                task.name,
                exc_info=True,
            )
        # Wake the dispatch loop immediately — no idle wait.
        self._task_available.set()
        log.debug(
            "Enqueued task: %s (priority=%d, queue_size=%d)",
            task.name,
            task.priority,
            self._task_queue.qsize(),
        )

    def pause(self) -> None:
        """Pause task dispatching.

        The dispatch loop finishes submitting the current task and then
        waits until resumed.  Tasks can still be enqueued while paused.
        """
        self._paused.clear()
        log.debug("Task queue paused")

    def resume(self) -> None:
        """Resume task dispatching.

        Dispatching resumes from where it was paused.
        """
        self._paused.set()
        log.debug("Task queue resumed")

    def stop(self) -> None:
        """Stop the dispatch thread and pool workers gracefully.

        Sets ``_running = False``, then wakes the dispatch loop so it can
        exit immediately.  The loop's ``finally`` block shuts the executor
        down (cancelling queued-but-not-started futures; already-running
        ones complete normally).  Waits up to 5 seconds for everything to
        finish.

        Any pending (callback, result) pairs left in ``_callback_queue``
        are discarded so that stale model callbacks from a previous test
        (or a discarded context) cannot fire after teardown.
        """
        log.debug("Stopping task queue worker")
        self._running = False
        self._paused.set()  # Unpause if paused
        # Wake the dispatch loop so it can observe _running=False without
        # waiting for the 0.5 s timeout.
        self._task_available.set()

        # Wait for the QThread (dispatch loop + executor shutdown) to finish.
        if not self.wait(5000):
            log.warning("Task queue worker did not stop within timeout")

        # Discard any pending callbacks.  Any invoke_callback ping events
        # already in the Qt event queue will call _drain_callback_queue,
        # which will safely find an empty queue and return immediately.
        while True:
            try:
                self._callback_queue.get_nowait()
            except queue.Empty:
                break

    def is_paused(self) -> bool:
        """Check if the worker is currently paused.

        Returns:
            True if paused, False otherwise.
        """
        return not self._paused.is_set()

    def queue_size(self) -> int:
        """Get the current number of tasks in the priority queue.

        Returns:
            Number of pending tasks (does not include tasks already
            submitted to the pool).
        """
        return self._task_queue.qsize()

    def _filter_queue(
        self, predicate: Callable[[AsyncTask, str], tuple[bool, bool]]
    ) -> int:
        """Filter queue items based on predicate function.

        Drains queue, applies predicate to each task, and rebuilds queue
        with filtered items. This is a generic helper for both cancel
        and clear operations.

        The entire drain-and-rebuild is performed while holding
        ``_queue_lock`` so that the dispatch thread cannot dequeue a task
        between two ``get_nowait()`` calls, making the operation atomic
        with respect to the dispatch loop.

        Note:
            Tasks already submitted to the pool cannot be removed here;
            the cancellation flag on :class:`AsyncTask` is the only
            mechanism that can stop an already-submitted task.

        Args:
            predicate: Function that takes (task, context_id) and returns
                (keep_in_queue, emit_cancelled_signal).

        Returns:
            Number of tasks affected (cancelled or removed).
        """
        affected_count = 0
        items_to_keep = []

        with self._queue_lock:
            while True:
                try:
                    priority, task = self._task_queue.get_nowait()
                    keep, emit_signal = predicate(task, task.context_id)

                    if keep:
                        items_to_keep.append((priority, task))
                    else:
                        affected_count += 1
                        if emit_signal:
                            self.task_cancelled.emit(
                                task.name, task.context_id
                            )

                except queue.Empty:
                    break

            # Rebuild queue with remaining items
            for item in items_to_keep:
                self._task_queue.put(item)

        return affected_count

    def clear_context_tasks(self, context_id: str) -> int:
        """Completely remove tasks for a specific context from queue.

        More aggressive than cancel - actually removes from queue rather
        than just marking as cancelled.

        Note:
            Tasks already submitted to the pool executor (i.e. currently
            running or waiting for a free pool slot) are *not* removed
            here.  Their results will be discarded by the model's stale-
            context check in the callback.

        Args:
            context_id: Context identifier to clear.

        Returns:
            Number of tasks removed.
        """

        def should_remove(task: AsyncTask, ctx: str) -> tuple[bool, bool]:
            """Return (keep_in_queue, emit_signal)."""
            if task.context_id == context_id and task.cancellable:
                return (False, True)  # Remove and signal
            return (True, False)  # Keep, no signal

        removed_count = self._filter_queue(should_remove)
        if removed_count > 0:
            log.debug(
                "Removed %d tasks for context: %s",
                removed_count,
                context_id,
            )

        return removed_count


# ---------------------------------------------------------------------------
# Module-level shared singleton
# ---------------------------------------------------------------------------

_shared_queue: AsyncTaskQueue | None = None
_shutdown_connected: bool = False


def get_task_queue() -> AsyncTaskQueue:
    """Return the shared AsyncTaskQueue, creating and starting it on first use.

    The queue is a module-level singleton so all components (table models,
    tree models, etc.) share one dispatch thread and one pool.

    On first creation the queue is automatically connected to
    ``QApplication.aboutToQuit`` so it stops cleanly when the application
    exits — no manual :func:`shutdown_task_queue` call is required.

    Returns:
        The running shared :class:`AsyncTaskQueue` instance.
    """
    global _shared_queue, _shutdown_connected
    if _shared_queue is None:
        from qtpy.QtWidgets import QApplication  # local import avoids circular

        _shared_queue = AsyncTaskQueue()
        _shared_queue.start()
        log.debug("Shared task queue started")

        app = QApplication.instance()
        if app is not None:
            if not _shutdown_connected:
                app.aboutToQuit.connect(shutdown_task_queue)
                _shutdown_connected = True
        else:
            log.warning(
                "get_task_queue() called before QApplication exists; "
                "automatic shutdown will not be registered."
            )

    return _shared_queue


def shutdown_task_queue() -> None:
    """Stop and discard the shared :class:`AsyncTaskQueue`.

    Called automatically when the ``QApplication`` emits ``aboutToQuit``
    (wired by :func:`get_task_queue` on first use).  Safe to call
    manually before that if an early teardown is needed; subsequent calls
    are no-ops.  After this call :func:`get_task_queue` will create a
    fresh queue on next access.
    """
    global _shared_queue
    if _shared_queue is not None:
        _shared_queue.stop()
        _shared_queue = None
        log.debug("Shared task queue stopped")
