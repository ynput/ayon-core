"""Unit tests for AsyncTaskQueue failure delivery."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from ayon_core.ui.components import task_queue
from ayon_core.ui.components.task_queue import AsyncTask, AsyncTaskQueue


def _failing_function() -> None:
    raise ValueError("boom")


class _SlowStartQueue(AsyncTaskQueue):
    """Queue with dispatch loop that begins after the stop was requested.

    Simulates a thread that did not get to run before 'stop' is called.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stop_called = threading.Event()

    def run(self) -> None:
        self._stop_called.wait(5)
        super().run()

    def wait(self, *args: Any) -> bool:
        self._stop_called.set()
        return super().wait(*args)


def test_stop_right_after_start_stops_dispatch_loop(qtbot) -> None:
    """A stop requested before the dispatch loop begins is not lost.

    The dispatch loop ran forever when it began after 'stop' was called,
    and the thread left running crashed the interpreter on its exit.
    """
    queue = _SlowStartQueue()
    queue.start()
    try:
        queue.stop()
        assert not queue.isRunning()
    finally:
        # Do not leave the thread running if the test fails
        queue.stop()


def test_failed_task_delivers_callback(qtbot) -> None:
    """A failed task reports ``None`` to its callback."""
    results: list[Any] = []
    queue = AsyncTaskQueue()
    task = AsyncTask(
        name="failing", function=_failing_function, callback=results.append
    )

    queue._run_task_in_pool(task)
    queue._drain_callback_queue()

    assert results == [None]


def test_failed_task_delivers_callback_when_logging_raises(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The callback is delivered even if logging the failure raises.

    Some hosts replace the standard streams with ones that raise when
    written to from a worker thread. Without the callback the requesting
    model would stay in its loading state forever.
    """

    def raising_log(*_args: Any, **_kwargs: Any) -> None:
        raise SystemError("<built-in function write> returned a result")

    monkeypatch.setattr(task_queue.log, "exception", raising_log)

    results: list[Any] = []
    queue = AsyncTaskQueue()
    task = AsyncTask(
        name="failing", function=_failing_function, callback=results.append
    )

    with pytest.raises(SystemError):
        queue._run_task_in_pool(task)
    queue._drain_callback_queue()

    assert results == [None]


def test_successful_task_delivers_single_callback_when_logging_raises(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing completion log does not turn a success into a failure.

    The result was already delivered, so a second ``None`` callback would
    make the requesting model believe the fetch failed.
    """

    def raising_log(*_args: Any, **_kwargs: Any) -> None:
        raise SystemError("<built-in function write> returned a result")

    def raising_completion_log(msg: str, *_args: Any, **_kwargs: Any) -> None:
        if msg.startswith("Task completed successfully"):
            raising_log()

    monkeypatch.setattr(task_queue.log, "debug", raising_completion_log)
    monkeypatch.setattr(task_queue.log, "exception", raising_log)

    results: list[Any] = []
    queue = AsyncTaskQueue()
    task = AsyncTask(
        name="successful", function=lambda: "value", callback=results.append
    )

    with pytest.raises(SystemError):
        queue._run_task_in_pool(task)
    queue._drain_callback_queue()

    assert results == ["value"]
