"""Unit tests for AsyncTaskQueue failure delivery."""

from __future__ import annotations

from typing import Any

import pytest
from ayon_core.ui.components import task_queue
from ayon_core.ui.components.task_queue import AsyncTask, AsyncTaskQueue


def _failing_function() -> None:
    raise ValueError("boom")


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
