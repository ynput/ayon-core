"""Tests for the background loads of the Browser inspector."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ayon_core.tools.browser.ui import browser_inspector
from ayon_core.tools.browser.ui.browser_inspector import ReviewInspector


class FakeTaskQueue:
    """Collect enqueued tasks instead of running them."""

    def __init__(self) -> None:
        self.tasks: list[Any] = []

    def clear_context_tasks(self, context_id: str) -> int:
        return 0

    def enqueue(self, task: Any) -> None:
        self.tasks.append(task)


class FakeImageCache:
    def __init__(self) -> None:
        self.paths: dict[str, str] = {}

    def get_path(self, key: str) -> str | None:
        return self.paths.get(key)


@pytest.fixture
def task_queue(monkeypatch: pytest.MonkeyPatch) -> FakeTaskQueue:
    queue = FakeTaskQueue()
    monkeypatch.setattr(browser_inspector, "get_task_queue", lambda: queue)
    monkeypatch.setattr(
        browser_inspector.shiboken, "isValid", lambda _obj: True
    )
    return queue


@pytest.fixture
def image_cache(monkeypatch: pytest.MonkeyPatch) -> FakeImageCache:
    cache = FakeImageCache()
    monkeypatch.setattr(
        browser_inspector.ImageCache,
        "get_instance",
        staticmethod(lambda: cache),
    )
    return cache


def _make_inspector() -> SimpleNamespace:
    """Stand-in for the inspector widget, no QApplication needed."""
    shown: dict[str, list[Any]] = {"repres": [], "thumbnails": []}
    return SimpleNamespace(
        shown=shown,
        _controller=SimpleNamespace(
            get_representation_items=lambda *_args: []
        ),
        _repre_request_key="",
        _repre_request_id=0,
        _thumb_request_id=0,
        _repre_context_id="inspector_repres_test",
        _current_thumb_key="",
        _representations=SimpleNamespace(
            set_items=lambda items, **_kwargs: shown["repres"].append(items)
        ),
        _thumbnail=SimpleNamespace(
            set_thumbnail=lambda paths: shown["thumbnails"].append(paths)
        ),
    )


def test_representations_not_reloaded_for_same_selection(
    task_queue: FakeTaskQueue,
) -> None:
    inspector = _make_inspector()

    ReviewInspector._load_representations(inspector, "demo", ["v1", "v2"])
    # Same selection again, e.g. click on an already selected version
    ReviewInspector._load_representations(inspector, "demo", ["v2", "v1"])
    assert len(task_queue.tasks) == 1

    task_queue.tasks[0].callback(["repre"])
    ReviewInspector._load_representations(inspector, "demo", ["v1", "v2"])
    assert len(task_queue.tasks) == 1
    assert inspector.shown["repres"] == [["repre"]]

    ReviewInspector._load_representations(inspector, "demo", ["v3"])
    assert len(task_queue.tasks) == 2


def test_representations_retry_after_failed_load(
    task_queue: FakeTaskQueue,
) -> None:
    inspector = _make_inspector()

    ReviewInspector._load_representations(inspector, "demo", ["v1"])
    # Failed tasks call the callback with 'None'
    task_queue.tasks[0].callback(None)
    ReviewInspector._load_representations(inspector, "demo", ["v1"])
    assert len(task_queue.tasks) == 2


def test_representations_refresh_ignores_older_request(
    task_queue: FakeTaskQueue,
) -> None:
    inspector = _make_inspector()

    ReviewInspector._load_representations(inspector, "demo", ["v1"])
    # Forced refresh while the first request is still running
    inspector._repre_request_key = ""
    ReviewInspector._load_representations(inspector, "demo", ["v1"])
    assert len(task_queue.tasks) == 2

    # Failure of the older request must not discard the newer result
    task_queue.tasks[0].callback(None)
    assert inspector.shown["repres"] == []
    task_queue.tasks[1].callback(["repre"])
    assert inspector.shown["repres"] == [["repre"]]

    ReviewInspector._load_representations(inspector, "demo", ["v1"])
    assert len(task_queue.tasks) == 2


def test_thumbnail_not_reloaded_for_same_selection(
    task_queue: FakeTaskQueue,
    image_cache: FakeImageCache,
) -> None:
    inspector = _make_inspector()
    keys = ["demo/v1/t1"]

    ReviewInspector._load_thumbnail(inspector, keys)
    ReviewInspector._load_thumbnail(inspector, keys)
    assert len(task_queue.tasks) == 1

    task_queue.tasks[0].callback("/tmp/t1.jpg")
    ReviewInspector._load_thumbnail(inspector, keys)
    assert len(task_queue.tasks) == 1
    assert inspector.shown["thumbnails"] == ["/tmp/t1.jpg"]


def test_thumbnail_retry_after_failed_load(
    task_queue: FakeTaskQueue,
    image_cache: FakeImageCache,
) -> None:
    inspector = _make_inspector()
    keys = ["demo/v1/t1"]

    ReviewInspector._load_thumbnail(inspector, keys)
    task_queue.tasks[0].callback("")
    ReviewInspector._load_thumbnail(inspector, keys)
    assert len(task_queue.tasks) == 2


def test_thumbnail_refresh_ignores_older_request(
    task_queue: FakeTaskQueue,
    image_cache: FakeImageCache,
) -> None:
    inspector = _make_inspector()
    keys = ["demo/v1/t1"]

    ReviewInspector._load_thumbnail(inspector, keys)
    # Forced refresh while the first request is still running
    inspector._current_thumb_key = ""
    ReviewInspector._load_thumbnail(inspector, keys)
    assert len(task_queue.tasks) == 2

    # Failure of the older request must not discard the newer result
    task_queue.tasks[0].callback("")
    assert inspector.shown["thumbnails"] == []
    task_queue.tasks[1].callback("/tmp/t1.jpg")
    assert inspector.shown["thumbnails"] == ["/tmp/t1.jpg"]

    ReviewInspector._load_thumbnail(inspector, keys)
    assert len(task_queue.tasks) == 2
