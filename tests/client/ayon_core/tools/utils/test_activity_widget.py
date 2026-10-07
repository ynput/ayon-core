"""Tests for the activity widget fed by a controller of a tool."""

from __future__ import annotations

import inspect
import uuid
from typing import Any
from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.common_models import StatusItem, UserItem
from ayon_core.tools.common_models.activities import (
    ActivityAnnotationItem,
    ActivityFileItem,
    ActivityItem,
)
from ayon_core.tools.utils import activity_widget
from ayon_core.tools.utils.activity_widget import (
    ActivityController,
    ActivityWidget,
)
from ayon_core.tools.workfiles.abstract import AbstractWorkfilesFrontend
from ayon_core.tools.workfiles.control import BaseWorkfileController
from ayon_core.ui.components import user_avatars
from ayon_core.ui.components.task_queue import AsyncTask
from ayon_core.ui.components.user_avatars import UserAvatarCache
from ayon_core.ui.data_models import (
    CommentModel,
    StatusChangeModel,
    VersionPublishModel,
)


class FakeController:
    """Controller with the methods of 'ActivityController' only."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.error: Exception | None = None
        self.thumbnail_path: str | None = "/cache/thumbnail.jpg"
        self.activity_items = [
            ActivityItem(
                activity_id="comment",
                activity_type="comment",
                author="libor",
                body="Looks good",
                created_at="2026-10-03T10:00:00+00:00",
                updated_at="2026-10-03T11:00:00+00:00",
                category="Feedback",
                files=[ActivityFileItem("file_id", "image/png")],
                annotations=[
                    ActivityAnnotationItem(
                        "annotation_id", [1001, 1002], "file_id", "other_id"
                    )
                ],
            ),
            ActivityItem(
                activity_id="status",
                activity_type="status.change",
                # Author is not filled for removed users
                author=None,
                updated_at="2026-10-02T10:00:00+00:00",
                product_name="modelMain",
                version_name="v003",
                old_status="In progress",
                new_status="Approved",
            ),
            ActivityItem(
                activity_id="publish",
                activity_type="version.publish",
                author="roy",
                updated_at="2026-10-01T10:00:00+00:00",
                product_name="modelMain",
                version_name="v003",
                version_id="version_id",
                version_status="Approved",
                thumbnail_id="t1",
            ),
            # Unknown types are skipped
            ActivityItem(activity_id="other", activity_type="reviewable"),
        ]

    def get_activity_items(
        self,
        project_name: str,
        entity_ids: list[str] | set[str],
        limit: int = 50,
    ) -> list[ActivityItem]:
        self.calls.append(("activities", project_name, entity_ids))
        if self.error is not None:
            raise self.error
        return list(self.activity_items)

    def get_project_status_items(
        self, project_name: str, sender: str | None = None
    ) -> list[StatusItem]:
        self.calls.append(("statuses", project_name))
        return [StatusItem("Approved", "#00f0b4", "APP", "task_alt", "done")]

    def get_user_items(self, project_name: str | None) -> list[UserItem]:
        self.calls.append(("users", project_name))
        return [
            UserItem("roy", "Roy Nieterau", "roy@example.com", None, True),
            UserItem("libor", None, None, None, True),
        ]

    def get_version_thumbnail_path(
        self, project_name: str, version_id: str, thumbnail_id: str
    ) -> str | None:
        self.calls.append(
            ("thumbnail", project_name, version_id, thumbnail_id)
        )
        if self.error is not None:
            raise self.error
        return self.thumbnail_path


class FakeTaskQueue:
    """Task queue running tasks in the main thread, when asked to."""

    def __init__(self) -> None:
        self.tasks: list[AsyncTask] = []

    def enqueue(self, task: AsyncTask) -> None:
        self.tasks.append(task)

    def clear_context_tasks(self, context_id: str) -> int:
        return 0

    def run(self, name_prefix: str = "") -> int:
        """Run pending tasks and their callbacks, like the real queue."""
        tasks = [
            task for task in self.tasks if task.name.startswith(name_prefix)
        ]
        for task in tasks:
            self.tasks.remove(task)
            task.callback(task.function())
        return len(tasks)


@pytest.fixture
def task_queue(monkeypatch: pytest.MonkeyPatch) -> FakeTaskQueue:
    queue = FakeTaskQueue()
    monkeypatch.setattr(activity_widget, "get_task_queue", lambda: queue)
    # Avatars are downloaded from the server by the avatar cache
    avatars_queue = FakeTaskQueue()
    monkeypatch.setattr(
        user_avatars, "get_task_queue", lambda: avatars_queue
    )
    return queue


@pytest.fixture
def project_name() -> str:
    # Thumbnails of the project are not in the image cache
    return f"demo_{uuid.uuid4().hex}"


class StreamCalls:
    """Record what the widget shows using the stream it inherits from."""

    def __init__(
        self, widget: ActivityWidget, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._depth = 0
        for name in (
            "set_status_definitions",
            "set_user_list",
            "set_activities",
            "set_message",
        ):
            monkeypatch.setattr(
                widget, name, self._wrap(name, getattr(widget, name))
            )

    def _wrap(self, name: str, method: Any) -> Any:
        def wrapper(value: Any, *args: Any, **kwargs: Any) -> Any:
            # A message is shown by setting no activities
            if not self._depth:
                self.calls.append((name, value))
            self._depth += 1
            try:
                return method(value, *args, **kwargs)
            finally:
                self._depth -= 1

        return wrapper

    def get(self, name: str) -> list[Any]:
        return [value for call_name, value in self.calls if call_name == name]


def _create_widget(qtbot, controller: FakeController) -> ActivityWidget:
    widget = ActivityWidget(controller)
    qtbot.addWidget(widget)
    return widget


def test_controller_is_required(qtbot):
    with pytest.raises(TypeError):
        ActivityWidget()


@pytest.mark.parametrize(
    "controller_class",
    [
        FakeController,
        BrowserWidgetController,
        AbstractWorkfilesFrontend,
        BaseWorkfileController,
    ],
)
def test_controllers_implement_the_interface(controller_class: type):
    methods = {
        name: method
        for name, method in vars(ActivityController).items()
        if inspect.isfunction(method) and not name.startswith("_")
    }
    assert set(methods) == {
        "get_activity_items",
        "get_project_status_items",
        "get_user_items",
        "get_version_thumbnail_path",
    }
    for name, method in methods.items():
        implemented = getattr(controller_class, name)
        assert (
            list(inspect.signature(implemented).parameters)
            == list(inspect.signature(method).parameters)
        ), name


def test_feed_is_fetched_from_the_controller_while_visible(
    qtbot, task_queue, monkeypatch, project_name
):
    controller = FakeController()
    widget = _create_widget(qtbot, controller)
    stream = StreamCalls(widget, monkeypatch)

    widget.set_context(project_name, ["b", "a", "a"])
    assert task_queue.tasks == []
    assert controller.calls == []

    widget.show()
    assert stream.get("set_message") == ["Loading activity…"]
    # Nothing is asked for in the main thread
    assert controller.calls == []
    assert task_queue.run() == 1
    assert controller.calls[:3] == [
        ("activities", project_name, ["a", "b"]),
        ("statuses", project_name),
        ("users", project_name),
    ]

    # Statuses and users are set before activities that are using them
    assert [name for name, _ in stream.calls[1:]] == [
        "set_status_definitions",
        "set_user_list",
        "set_activities",
    ]
    assert stream.get("set_status_definitions") == [
        [
            {
                "text": "Approved",
                "short_text": "APP",
                "icon": "task_alt",
                "color": "#00f0b4",
            }
        ]
    ]
    assert [
        (user.name, user.short_name, user.full_name)
        for user in stream.get("set_user_list")[0]
    ] == [("roy", "roy", "Roy Nieterau"), ("libor", "libor", "libor")]

    comment, status, publish = stream.get("set_activities")[0]
    assert isinstance(comment, CommentModel)
    assert comment.activity_id == "comment"
    assert comment.comment == "Looks good"
    assert comment.comment_date == "2026-10-03T11:00:00+00:00"
    assert comment.category == "Feedback"
    # Falls back to the username when the full name is not filled
    assert (comment.user_name, comment.user_full_name) == ("libor", "libor")
    assert [(file.id, file.mime, file.frame) for file in comment.files] == [
        ("file_id", "image/png", 1001)
    ]
    assert [
        (annotation.id, annotation.range, annotation.composite)
        for annotation in comment.annotations
    ] == [("annotation_id", [1001, 1002], "file_id")]

    assert isinstance(status, StatusChangeModel)
    assert (status.user_name, status.user_full_name) == ("n/a", "n/a")
    assert (status.product, status.version) == ("modelMain", "v003")
    assert (status.old_status, status.new_status) == (
        "In progress",
        "Approved",
    )

    assert isinstance(publish, VersionPublishModel)
    assert (publish.user_name, publish.user_full_name) == (
        "roy",
        "Roy Nieterau",
    )
    assert (publish.product, publish.version) == ("modelMain", "v003")
    assert publish.date == "2026-10-01T10:00:00+00:00"
    assert publish.status == "Approved"
    assert publish.thumbnail_key
    assert widget.activity_count() == 3

    # The same context is not fetched again
    widget.set_context(project_name, ["a", "b"])
    assert task_queue.run("activity_widget_feed") == 0
    widget.refresh()
    assert task_queue.run("activity_widget_feed") == 1


def test_publish_thumbnail_is_loaded_by_the_controller(
    qtbot, task_queue, project_name, tmp_path
):
    from qtpy import QtGui

    image_path = str(tmp_path / "thumbnail.png")
    pixmap = QtGui.QPixmap(8, 8)
    pixmap.fill(QtGui.QColor("red"))
    assert pixmap.save(image_path)

    controller = FakeController()
    controller.thumbnail_path = image_path
    widget = _create_widget(qtbot, controller)
    widget.show()
    widget.set_context(project_name, ["version_id"])
    task_queue.run("activity_widget_feed")
    del controller.calls[:]

    # The thumbnail of the publish asks for its image
    assert task_queue.run("activity_widget_thumbnail_") == 1
    assert controller.calls == [
        ("thumbnail", project_name, "version_id", "t1")
    ]


def test_thumbnail_loader_passes_only_available_paths(
    qtbot, task_queue, project_name
):
    controller = FakeController()
    widget = _create_widget(qtbot, controller)
    widget.show()
    widget.set_context(project_name, ["version_id"])
    task_queue.run("activity_widget_feed")
    del task_queue.tasks[:], controller.calls[:]
    key = next(iter(widget._thumbnail_sources))
    loaded = []

    widget._load_thumbnail(key, loaded.append)
    widget._load_thumbnail("unknown key", loaded.append)
    assert task_queue.run() == 1
    assert loaded == ["/cache/thumbnail.jpg"]

    controller.thumbnail_path = None
    widget._load_thumbnail(key, loaded.append)
    controller.error = RuntimeError("Server is not available")
    widget._load_thumbnail(key, loaded.append)
    assert task_queue.run() == 2
    assert loaded == ["/cache/thumbnail.jpg"]
    assert controller.calls == [
        ("thumbnail", project_name, "version_id", "t1")
    ] * 3


def test_failed_fetch_shows_a_message_and_can_be_retried(
    qtbot, task_queue, monkeypatch, project_name
):
    controller = FakeController()
    controller.error = RuntimeError("Server is not available")
    widget = _create_widget(qtbot, controller)
    stream = StreamCalls(widget, monkeypatch)
    widget.show()
    widget.set_context(project_name, ["a"])
    task_queue.run()

    assert stream.get("set_message")[-1] == "Could not load activity"
    assert stream.get("set_activities") == []

    # Selecting the same context again tries once more
    controller.error = None
    widget.set_context(project_name, ["a"])
    assert task_queue.run("activity_widget_feed") == 1
    assert len(stream.get("set_activities")) == 1
    assert widget.activity_count() == 3


def test_result_of_a_previous_context_is_ignored(
    qtbot, task_queue, monkeypatch, project_name
):
    controller = FakeController()
    widget = _create_widget(qtbot, controller)
    stream = StreamCalls(widget, monkeypatch)
    widget.show()
    widget.set_context(project_name, ["a"])
    stale_task = task_queue.tasks.pop()

    controller.activity_items = controller.activity_items[:1]
    widget.set_context(project_name, ["b"])
    # The first fetch was running already and finishes later
    stale_result = stale_task.function()
    task_queue.run()
    stale_task.callback(stale_result)

    assert len(stream.get("set_activities")) == 1
    assert widget.activity_count() == 1

    widget.set_context(None, [], "Select something")
    assert task_queue.tasks == []
    assert stream.get("set_message")[-1] == "Select something"
    assert widget.activity_count() == 0


def test_workfiles_side_panel_uses_its_controller(qtbot, task_queue):
    from ayon_core.tools.workfiles.widgets.side_panel import SidePanelWidget

    controller = BaseWorkfileController()
    controller._current_project_name = "demo"
    panel = SidePanelWidget(controller, None)
    qtbot.addWidget(panel)
    widget = panel._activity_widget
    assert widget._controller is controller

    # Activity of the folder is shown until a task is selected
    controller.emit_event(
        "selection.folder.changed", {"folder_id": "folder_id"}
    )
    assert (widget._project_name, widget._entity_ids) == (
        "demo",
        ("folder_id",),
    )
    controller.emit_event(
        "selection.task.changed",
        {"folder_id": "folder_id", "task_id": "task_id", "task_name": "a"},
    )
    assert widget._entity_ids == ("task_id",)
    # The activity tab is not opened
    assert task_queue.tasks == []


def test_browser_inspector_uses_its_controller(qtbot, monkeypatch):
    from ayon_core.tools.browser.control import BrowserController
    from ayon_core.tools.browser.ui.browser_inspector import ReviewInspector

    # The Site Sync column provider looks up the addon on creation.
    addon_manager = Mock()
    addon_manager.get.return_value = None
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager",
        lambda: addon_manager,
    )
    controller = BrowserWidgetController(BrowserController())
    avatar_cache = UserAvatarCache()
    inspector = ReviewInspector(controller, avatar_cache=avatar_cache)
    qtbot.addWidget(inspector)

    assert inspector._activity._controller is controller
    assert inspector._activity._avatar_cache is avatar_cache


def test_activity_widget_shares_a_passed_avatar_cache(qtbot):
    controller = FakeController()
    shared_cache = UserAvatarCache()
    shared = ActivityWidget(controller, avatar_cache=shared_cache)
    qtbot.addWidget(shared)
    assert shared._avatar_cache is shared_cache
    assert not shared.findChildren(UserAvatarCache)

    # One is created for a widget that is used on its own
    alone = _create_widget(qtbot, controller)
    assert isinstance(alone._avatar_cache, UserAvatarCache)
    assert alone._avatar_cache is not shared_cache
