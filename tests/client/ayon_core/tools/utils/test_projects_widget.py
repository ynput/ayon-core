"""Tests for thumbnails in projects widgets."""

from __future__ import annotations

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.tools.common_models import ProjectItem
from ayon_core.tools.utils import projects_widget
from ayon_core.tools.utils.projects_widget import (
    PROJECT_NAME_ROLE,
    ProjectsCombobox,
    ProjectsWidget,
)
from ayon_core.ui.components.task_queue import shutdown_task_queue


class _Controller:
    def __init__(self, project_items, thumbnail_path):
        self.project_items = project_items
        self.thumbnail_path = thumbnail_path
        self.calls = []

    def register_event_callback(self, topic, callback):
        pass

    def get_project_items(self, sender=None):
        return self.project_items

    def set_selected_project(self, project_name):
        pass

    def get_thumbnail_paths(self, project_name, entity_type, entity_ids):
        self.calls.append((project_name, entity_type, set(entity_ids)))
        return {
            entity_id: (
                self.thumbnail_path
                if entity_id.startswith("thumbnail")
                else None
            )
            for entity_id in entity_ids
        }


class _ControllerWithoutThumbnails:
    def __init__(self, project_items):
        self.project_items = project_items

    def register_event_callback(self, topic, callback):
        pass

    def get_project_items(self, sender=None):
        return self.project_items

    def set_selected_project(self, project_name):
        pass


def _project_items():
    return [
        ProjectItem(
            name,
            True,
            False,
            MaterialSymbolsIcon("map"),
            is_pinned=name.endswith("pinned"),
        )
        for name in (
            "thumbnail_pinned",
            "thumbnail_project",
            "plain_pinned",
            "plain_project",
        )
    ]


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


def _find_index(view, project_name):
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(PROJECT_NAME_ROLE) == project_name:
            return index
    raise AssertionError(f"Project '{project_name}' was not found")


def _get_option(view, index):
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = view.visualRect(index)
    option.decorationSize = QtCore.QSize(16, 16)
    option.state = QtWidgets.QStyle.StateFlag.State_Enabled
    return option


def _wait_for_thumbnails(qtbot, widget):
    loader = widget._thumbnails_painter._loader
    qtbot.waitUntil(
        lambda: loader.get_pixmap("thumbnail_project") is not None
    )


def _assert_thumbnails_are_left_of_pin(view, delegate):
    """Thumbnail is always at the same position, next to the pin icon."""
    rights = set()
    for project_name in ("thumbnail_pinned", "thumbnail_project"):
        index = _find_index(view, project_name)
        option = _get_option(view, index)
        item_rect = delegate._get_thumbnail_item_rect(option, index)
        pin_left = option.rect.right() - delegate._get_pin_width(option)
        assert item_rect.right() <= pin_left
        # Project name is elided before the thumbnail
        assert delegate._get_reserved_right_width(option, index) > (
            option.rect.right() - item_rect.right()
        )
        rights.add(item_rect.right() - option.rect.left())
    assert len(rights) == 1

    # Space is not reserved for projects without thumbnail
    index = _find_index(view, "plain_project")
    option = _get_option(view, index)
    assert delegate._get_reserved_right_width(option, index) == 0
    # Pin icon does not overlap the project name
    index = _find_index(view, "plain_pinned")
    option = _get_option(view, index)
    assert delegate._get_reserved_right_width(
        option, index
    ) == delegate._get_pin_width(option)


def test_projects_widget_shows_thumbnails(qtbot, task_queue, thumbnail_path):
    controller = _Controller(_project_items(), thumbnail_path)
    widget = ProjectsWidget(controller)
    qtbot.addWidget(widget)
    widget.resize(300, 300)
    widget.show()
    qtbot.waitExposed(widget)
    # Nothing is requested until the projects are painted
    assert not controller.calls

    with qtbot.waitSignal(widget.refreshed):
        widget.refresh()
    _wait_for_thumbnails(qtbot, widget)

    requested_names = set()
    for project_name, entity_type, entity_ids in controller.calls:
        assert project_name is None
        assert entity_type == "project"
        requested_names |= entity_ids
    assert requested_names == {
        project_item.name for project_item in controller.project_items
    }
    _assert_thumbnails_are_left_of_pin(
        widget._projects_view, widget._projects_delegate
    )


def test_projects_combobox_shows_thumbnails_in_popup(
    qtbot, task_queue, thumbnail_path
):
    controller = _Controller(_project_items(), thumbnail_path)
    widget = ProjectsCombobox(controller, None)
    qtbot.addWidget(widget)
    widget.resize(300, 30)
    widget.show()
    qtbot.waitExposed(widget)
    with qtbot.waitSignal(widget.refreshed):
        widget.refresh()

    qtbot.wait(widget._thumbnails_painter._request_delay * 3)
    # Thumbnails are not requested until the popup is shown
    assert not controller.calls

    combobox = widget._projects_combobox
    combobox.showPopup()
    try:
        _wait_for_thumbnails(qtbot, widget)
        assert {
            entity_type for _, entity_type, _ in controller.calls
        } == {"project"}
        _assert_thumbnails_are_left_of_pin(
            combobox.view(), widget._combobox_delegate
        )
    finally:
        combobox.hidePopup()


def test_controller_without_thumbnails_uses_own_model(
    qtbot, task_queue, thumbnail_path, monkeypatch
):
    """Controller does not implement 'get_thumbnail_paths'.

    That is the case for tools of other addons, e.g. tray publisher.
    """
    models = []

    class _ThumbnailsModel(_Controller):
        def __init__(self):
            super().__init__([], thumbnail_path)
            self.reset_count = 0
            models.append(self)

        def reset(self):
            self.reset_count += 1

    monkeypatch.setattr(projects_widget, "ThumbnailsModel", _ThumbnailsModel)

    controller = _ControllerWithoutThumbnails(_project_items())
    widget = ProjectsWidget(controller)
    qtbot.addWidget(widget)
    widget.resize(300, 300)
    widget.show()
    qtbot.waitExposed(widget)
    with qtbot.waitSignal(widget.refreshed):
        widget.refresh()
    _wait_for_thumbnails(qtbot, widget)

    assert len(models) == 1
    assert {entity_type for _, entity_type, _ in models[0].calls} == {
        "project"
    }
    # Changed thumbnails are received on refresh
    assert models[0].reset_count == 1

    widget.set_thumbnails_visible(False)
    assert not widget._thumbnails_painter.is_enabled()
