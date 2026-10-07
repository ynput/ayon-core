"""Tests for deferred loading of entity thumbnails."""

from __future__ import annotations

import sys
import threading
import types

import pytest
from qtpy import QtCore, QtGui, QtWidgets

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.utils.entity_thumbnails import (
    EntityThumbnailsLoader,
    EntityThumbnailsPainter,
)
from ayon_core.ui.components.task_queue import shutdown_task_queue

THUMBNAIL_SIZE = QtCore.QSize(32, 18)
ENTITY_ID_ROLE = QtCore.Qt.UserRole + 1


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


def test_thumbnail_has_rounded_corners(qtbot, task_queue, thumbnail_path):
    controller = _Controller({"a": thumbnail_path})
    loader = EntityThumbnailsLoader(
        controller, "folder", THUMBNAIL_SIZE, radius=4
    )
    loader.set_project_name("demo")
    with qtbot.waitSignal(loader.thumbnails_changed):
        loader.load(["a"], 1.0)

    image = loader.get_pixmap("a").toImage()
    assert image.pixelColor(0, 0).alpha() == 0
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    assert center.alpha() == 255
    assert center.red() == 255


def test_old_pixmaps_are_removed_and_loaded_again(
    qtbot, task_queue, tmp_path
):
    paths = {}
    for idx in range(6):
        image = QtGui.QImage(8, 8, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("red"))
        path = str(tmp_path / f"thumbnail_{idx}.png")
        assert image.save(path)
        paths[f"entity_{idx}"] = path

    controller = _Controller(paths)
    loader = _create_loader(controller)
    loader.max_pixmaps = 4
    entity_ids = list(paths)
    for entity_id in entity_ids:
        with qtbot.waitSignal(loader.thumbnails_changed):
            loader.load([entity_id], 1.0)

    assert len(loader._pixmap_by_path) <= loader.max_pixmaps
    # The first loaded was removed and is loaded again on next request
    assert loader.get_pixmap(entity_ids[0]) is None
    assert loader.needs_load(entity_ids[0])
    # The last loaded is still available
    assert loader.get_pixmap(entity_ids[-1]) is not None
    assert not loader.needs_load(entity_ids[-1])


class _ThumbnailsDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, thumbnails_painter, parent):
        super().__init__(parent)
        self._thumbnails_painter = thumbnails_painter

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        self._thumbnails_painter.paint(painter, option.rect, index)


def _create_view(qtbot, controller, width):
    model = QtGui.QStandardItemModel()
    for idx in range(300):
        item = QtGui.QStandardItem(f"Item {idx}")
        item.setData(f"entity_{idx}", ENTITY_ID_ROLE)
        model.appendRow(item)
    view = QtWidgets.QTreeView()
    qtbot.addWidget(view)
    view.setModel(model)
    view.setHeaderHidden(True)
    thumbnails_painter = EntityThumbnailsPainter(
        view, controller, "folder", ENTITY_ID_ROLE
    )
    view.setItemDelegate(_ThumbnailsDelegate(thumbnails_painter, view))
    thumbnails_painter.set_project_name("demo")
    view.resize(width, 200)
    view.show()
    qtbot.waitExposed(view)
    return view, thumbnails_painter


def test_only_visible_items_are_requested(qtbot, task_queue):
    controller = _Controller({})
    view, thumbnails_painter = _create_view(qtbot, controller, 400)
    loader = thumbnails_painter._loader
    qtbot.waitUntil(
        lambda: bool(loader._valid_ids) and not loader._loading_ids
    )

    requested_ids = set()
    for _project_name, _entity_type, entity_ids in controller.calls:
        requested_ids |= entity_ids
    assert "entity_0" in requested_ids
    # Much less than all items, only those in the viewport
    assert len(requested_ids) < 50
    assert "entity_299" not in requested_ids


def test_thumbnails_are_not_requested_in_narrow_view(qtbot, task_queue):
    controller = _Controller({})
    view, thumbnails_painter = _create_view(qtbot, controller, 100)
    qtbot.wait(thumbnails_painter._request_delay * 3)

    assert not thumbnails_painter._requested
    assert not controller.calls


def test_images_are_loaded_by_more_threads_at_once(
    qtbot, task_queue, tmp_path
):
    """More background tasks load images at the same time.

    The application could freeze with PySide6 when Qt functions were
    called for the first time from more threads at the same moment. This
    test does not finish if that happens.
    """
    paths = {}
    for idx in range(64):
        image = QtGui.QImage(64, 64, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("green"))
        path = str(tmp_path / f"concurrent_{idx}.png")
        assert image.save(path)
        paths[f"entity_{idx}"] = path

    controller = _Controller(paths)
    loader = EntityThumbnailsLoader(
        controller, "folder", THUMBNAIL_SIZE, radius=2
    )
    loader.set_project_name("demo")
    loader.load(list(paths), 1.0)
    # Entities are split to more tasks processed by more threads
    qtbot.waitUntil(lambda: not loader._loading_ids, timeout=30000)

    assert len(controller.thread_ids) > 1
    assert all(
        loader.get_pixmap(entity_id) is not None
        for entity_id in paths
    )
