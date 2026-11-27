"""Tests for the user avatars in the 'Author' column of workfiles tool."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.common_models import UserItem
from ayon_core.tools.workfiles.widgets import (
    files_widget_published,
    files_widget_workarea,
)
from ayon_core.tools.workfiles.widgets.utils import (
    USERNAME_ROLE,
    WorkfilesDelegate,
)
from ayon_core.ui.components import user_avatars


class _Controller:
    def register_event_callback(self, topic, callback) -> None:
        pass

    def get_user_items_by_name(self):
        return {"roy": UserItem("roy", "Roy Nieterau", None, None, True)}

    def get_workarea_file_items(self, folder_id, task_name):
        return [
            SimpleNamespace(
                filepath=f"/work/sh010_comp_v{idx:03d}.nk",
                rootless_path=f"{{root}}/sh010_comp_v{idx:03d}.nk",
                available=True,
                updated_by=updated_by,
                workfile_entity_id=str(idx),
                file_modified=1000.0 * idx,
            )
            for idx, updated_by in enumerate(
                ("roy", "unknown.user", None), 1
            )
        ]

    def get_published_file_items(self, folder_id, task_id):
        return [
            SimpleNamespace(
                representation_id="repre-1",
                filepath="/publish/sh010_workfile_v001.nk",
                available=True,
                author="roy",
                file_modified=1000.0,
            )
        ]


@pytest.fixture
def avatar_tasks(qapp, monkeypatch):
    """Avatars are requested, but never downloaded."""
    tasks = []

    class _Queue:
        def enqueue(self, task) -> None:
            tasks.append(task)

    monkeypatch.setattr(user_avatars, "get_task_queue", _Queue)
    return tasks


def _init_option(model, row: int, column: int = 1):
    delegate = WorkfilesDelegate(user_avatars.UserAvatarCache(model))
    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(option, model.index(row, column))
    return option


def test_workarea_author_has_avatar(avatar_tasks):
    model = files_widget_workarea.WorkAreaFilesModel(_Controller())
    model._on_task_changed({"folder_id": "f", "task_name": "comp"})

    # Full name is displayed, the avatar is found by the username
    index = model.index(0, 1)
    assert index.data(QtCore.Qt.DisplayRole) == "Roy Nieterau"
    assert index.data(USERNAME_ROLE) == "roy"
    option = _init_option(model, 0)
    assert option.text == "Roy Nieterau"
    assert not option.icon.isNull()
    avatar_size = user_avatars.ITEM_AVATAR_SIZE
    assert option.decorationSize == QtCore.QSize(avatar_size, avatar_size)
    # The avatar itself is downloaded in the background
    assert [task.name for task in avatar_tasks] == ["fetch_avatar:roy"]

    # User that is not on the project anymore
    assert model.index(1, 1).data(QtCore.Qt.DisplayRole) == "unknown.user"
    assert not _init_option(model, 1).icon.isNull()

    # Workfile without a user
    assert model.index(2, 1).data(USERNAME_ROLE) is None
    assert _init_option(model, 2).icon.isNull()

    # Other columns are not affected
    assert _init_option(model, 0, column=2).icon.isNull()


def test_published_author_has_avatar(avatar_tasks):
    model = files_widget_published.PublishedFilesModel(_Controller())
    model._on_folder_changed({"folder_id": "f"})
    model.set_published_mode(True)

    index = model.index(0, 1)
    assert index.data(QtCore.Qt.DisplayRole) == "Roy Nieterau"
    assert index.data(USERNAME_ROLE) == "roy"
    assert not _init_option(model, 0).icon.isNull()


def test_avatar_download_repaints_the_view(qtbot, avatar_tasks):
    widget = files_widget_workarea.WorkAreaFilesWidget(_Controller(), None)
    qtbot.addWidget(widget)
    avatar_cache = widget._work_files_delegate._avatar_cache
    paints = []

    class _PaintFilter(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Paint:
                paints.append(event.type())
            return False

    paint_filter = _PaintFilter()
    widget._view.viewport().installEventFilter(paint_filter)
    widget.show()
    qtbot.waitUntil(lambda: bool(paints), timeout=5000)
    paints.clear()

    avatar_cache.avatar_updated.emit("roy")
    qtbot.waitUntil(lambda: bool(paints), timeout=5000)


def test_avatar_is_not_jagged_on_scaled_screen(avatar_tasks):
    """Avatar is filtered when it does not match pixels of the screen.

    With 125% scaling of a screen the 18px avatar covers 22.5 pixels. It
    cannot be painted pixel for pixel, without filtering some of its rows
    and columns are doubled, which shows as jagged edges.
    """
    scale = 1.25
    model = files_widget_workarea.WorkAreaFilesModel(_Controller())
    model._on_task_changed({"folder_id": "f", "task_name": "comp"})
    avatar_cache = user_avatars.UserAvatarCache(model)
    delegate = WorkfilesDelegate(avatar_cache)

    # Avatar of black and white pixels, as rendered for the scaled screen
    size = user_avatars.ITEM_AVATAR_SIZE
    pixel_size = int(size * scale)
    avatar = QtGui.QImage(
        pixel_size, pixel_size, QtGui.QImage.Format_ARGB32
    )
    for x in range(pixel_size):
        for y in range(pixel_size):
            color = QtCore.Qt.black if (x + y) % 2 else QtCore.Qt.white
            avatar.setPixelColor(x, y, QtGui.QColor(color))
    avatar.setDevicePixelRatio(scale)
    avatar_cache._pixmaps[("roy", size)] = QtGui.QPixmap.fromImage(avatar)

    cell_rect = QtCore.QRect(0, 0, 120, 28)
    image = QtGui.QImage(
        int(cell_rect.width() * scale),
        int(cell_rect.height() * scale),
        QtGui.QImage.Format_ARGB32,
    )
    image.setDevicePixelRatio(scale)
    image.fill(QtCore.Qt.black)
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = cell_rect
    option.state = QtWidgets.QStyle.State_Enabled
    painter = QtGui.QPainter(image)
    delegate.paint(painter, option, model.index(0, 1))
    painter.end()

    # Inner pixels of the avatar, away from its edges and the name
    values = {
        image.pixelColor(x, y).red()
        for x in range(14, 28)
        for y in range(10, 24)
    }
    # Only black and white pixels would mean pixels were just repeated
    assert values - {0, 255}
