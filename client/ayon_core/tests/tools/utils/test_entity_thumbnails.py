"""Tests for deferred loading of entity thumbnails."""

from __future__ import annotations

import sys
import threading
import types

import pytest
from qtpy import QtCore, QtGui

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.utils.entity_thumbnails import EntityThumbnailsLoader
from ayon_core.ui.components.task_queue import shutdown_task_queue

THUMBNAIL_SIZE = QtCore.QSize(32, 18)


class _Controller:
    def __init__(self, path_by_entity_id):
        self.path_by_entity_id = path_by_entity_id
        self.calls = []
        self.thread_ids = set()

    def get_thumbnail_paths(self, project_name, entity_type, entity_ids):
        self.thread_ids.add(threading.get_ident())
        self.calls.append((project_name, entity_type, set(entity_ids)))
        return {
            entity_id: self.path_by_entity_id.get(entity_id)
            for entity_id in entity_ids
        }


@pytest.fixture
def thumbnail_path(tmp_path, qapp):
    image = QtGui.QImage(64, 64, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("red"))
    path = str(tmp_path / "thumbnail.png")
    assert image.save(path)
    return path


@pytest.fixture
def task_queue(qapp):
    yield
    shutdown_task_queue()


def _create_loader(controller):
    loader = EntityThumbnailsLoader(controller, "folder", THUMBNAIL_SIZE)
    loader.set_project_name("demo")
    return loader


def test_thumbnails_are_loaded_in_background(
    qtbot, task_queue, thumbnail_path
):
    controller = _Controller({"a": thumbnail_path, "b": None})
    loader = _create_loader(controller)

    assert loader.get_pixmap("a") is None
    with qtbot.waitSignal(loader.thumbnails_changed) as blocker:
        loader.load({"a", "b"}, 2.0)

    # Only entities with thumbnail are reported as changed
    assert blocker.args == [["a"]]
    assert threading.get_ident() not in controller.thread_ids
    assert controller.calls == [("demo", "folder", {"a", "b"})]

    pixmap = loader.get_pixmap("a")
    # Image is scaled and cropped to the thumbnail size
    assert pixmap.size() == THUMBNAIL_SIZE * 2
    assert pixmap.devicePixelRatio() == 2.0
    assert loader.get_pixmap("b") is None


def test_loaded_thumbnails_are_not_requested_again(
    qtbot, task_queue, thumbnail_path
):
    controller = _Controller({"a": thumbnail_path})
    loader = _create_loader(controller)
    with qtbot.waitSignal(loader.thumbnails_changed):
        loader.load({"a"}, 1.0)

    assert not loader.needs_load("a")
    loader.load({"a"}, 1.0)
    assert len(controller.calls) == 1

    # Thumbnail is validated after refresh, but stays available
    loader.set_outdated()
    assert loader.needs_load("a")
    assert loader.get_pixmap("a") is not None
    loader.load({"a"}, 1.0)
    qtbot.waitUntil(lambda: "a" in loader._valid_ids)
    assert len(controller.calls) == 2


def test_failed_load_is_not_repeated(qtbot, task_queue):
    controller = _Controller({})
    controller.get_thumbnail_paths = None
    loader = _create_loader(controller)
    loader.load({"a"}, 1.0)
    # Entity is in loading state until the task finishes
    assert not loader.needs_load("a")
    qtbot.waitUntil(lambda: "a" in loader._valid_ids)
    assert not loader.needs_load("a")
    assert loader.get_pixmap("a") is None


def test_project_change_forgets_thumbnails(
    qtbot, task_queue, thumbnail_path
):
    controller = _Controller({"a": thumbnail_path})
    loader = _create_loader(controller)
    with qtbot.waitSignal(loader.thumbnails_changed):
        loader.load({"a"}, 1.0)

    loader.set_project_name("other")
    assert loader.get_pixmap("a") is None
    assert loader.needs_load("a")


def test_controller_without_thumbnails(qapp):
    loader = EntityThumbnailsLoader(object(), "folder", THUMBNAIL_SIZE)
    loader.set_project_name("demo")
    assert not loader.is_available()
    loader.load({"a"}, 1.0)
    assert loader.needs_load("a")


def test_changed_thumbnail_is_updated_after_refresh(
    qtbot, task_queue, thumbnail_path, tmp_path
):
    controller = _Controller({"a": thumbnail_path, "b": None})
    loader = _create_loader(controller)
    with qtbot.waitSignal(loader.thumbnails_changed):
        loader.load({"a", "b"}, 1.0)
    old_pixmap = loader.get_pixmap("a")

    # New thumbnails were set on the entities
    image = QtGui.QImage(64, 64, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("blue"))
    new_path = str(tmp_path / "new_thumbnail.png")
    assert image.save(new_path)
    controller.path_by_entity_id = {"a": new_path, "b": thumbnail_path}

    loader.set_outdated()
    with qtbot.waitSignal(loader.thumbnails_changed) as blocker:
        loader.load({"a", "b"}, 1.0)

    assert sorted(blocker.args[0]) == ["a", "b"]
    assert loader.get_pixmap("a").cacheKey() != old_pixmap.cacheKey()
    assert loader.get_pixmap("b") is not None
