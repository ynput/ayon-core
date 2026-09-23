"""AsyncLoader: latest request wins, errors and loading state."""

from __future__ import annotations

import threading

import pytest

from ayon_core.ui.components import async_loader
from ayon_core.ui.components.async_loader import AsyncLoader


class _TaskQueue:
    """Collects tasks instead of running them in worker threads."""

    def __init__(self):
        self.tasks = []

    def enqueue(self, task):
        self.tasks.append(task)

    def run(self, task):
        self.tasks.remove(task)
        result = task.function()
        if not task.is_cancelled():
            task.callback(result)


@pytest.fixture
def task_queue(qapp, monkeypatch):
    queue = _TaskQueue()
    monkeypatch.setattr(async_loader, "get_task_queue", lambda: queue)
    return queue


def test_result_is_applied_and_loading_signalled(task_queue):
    loader = AsyncLoader("test")
    states = []
    applied = []
    loader.loading_changed.connect(states.append)

    loader.request(lambda: 42, applied.append)
    assert loader.is_loading()
    task_queue.run(task_queue.tasks[0])

    assert applied == [42]
    assert states == [True, False]
    assert not loader.is_loading()


def test_only_latest_request_is_applied(task_queue):
    loader = AsyncLoader("test")
    applied = []

    loader.request(lambda: "first", applied.append)
    first = task_queue.tasks[0]
    first_result = first.function()
    loader.request(lambda: "second", applied.append)
    second = task_queue.tasks[1]

    assert first.is_cancelled()
    # First finished in a worker before it was cancelled
    first.callback(first_result)
    assert applied == []
    assert loader.is_loading()

    task_queue.run(second)
    assert applied == ["second"]
    assert not loader.is_loading()


def test_failed_fetch_calls_on_error(task_queue):
    loader = AsyncLoader("test")
    applied = []
    errors = []

    def fetch():
        raise ValueError("boom")

    loader.request(fetch, applied.append, errors.append)
    task_queue.run(task_queue.tasks[0])

    assert applied == []
    assert [str(exc) for exc in errors] == ["boom"]
    assert not loader.is_loading()


def test_cancel_drops_result(task_queue):
    loader = AsyncLoader("test")
    applied = []
    loader.request(lambda: 1, applied.append)
    task = task_queue.tasks[0]
    result = task.function()

    loader.cancel()
    task.callback(result)

    assert applied == []
    assert not loader.is_loading()


def test_fetch_runs_in_worker_and_apply_in_main_thread(qtbot):
    loader = AsyncLoader("test")
    threads = {}

    def fetch():
        threads["fetch"] = threading.current_thread()
        return True

    def apply(_result):
        threads["apply"] = threading.current_thread()

    loader.request(fetch, apply)
    qtbot.waitUntil(lambda: not loader.is_loading(), timeout=5000)

    assert threads["fetch"] is not threading.main_thread()
    assert threads["apply"] is threading.main_thread()
