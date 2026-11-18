"""Tests for going to a context on the hierarchy page of the launcher."""

from __future__ import annotations

import time
from typing import Optional

import pytest
from qtpy import QtWidgets

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.tools.common_models import FolderItem, TaskItem
from ayon_core.tools.launcher.models import (
    LauncherExpectedSelection,
    LauncherSelectionModel,
)
from ayon_core.tools.launcher.ui.hierarchy_page import (
    LauncherFoldersWidget,
    LauncherTasksWidget,
)

FOLDER_NAMES = ("sh020", "sh030")
TASK_NAMES = ("animation", "layout")


class FakeController:
    """What the folders and tasks widgets ask of the launcher controller.

    Project 'test' has two folders with tasks of the same names, project
    'other' has no folders.
    """

    def __init__(self) -> None:
        self._event_system = QueuedEventSystem()
        self._selection = LauncherSelectionModel(self)
        self._expected = LauncherExpectedSelection(self)

    def register_event_callback(self, topic, callback) -> None:
        self._event_system.add_callback(topic, callback)

    def emit_event(self, topic, data=None, source=None) -> None:
        self._event_system.emit(topic, data or {}, source)

    def get_folder_items(self, project_name, sender=None):
        if project_name != "test":
            return {}
        return {
            name: FolderItem(
                entity_id=name,
                parent_id=None,
                name=name,
                path=f"/{name}",
                folder_type="Shot",
                label=name,
                status="",
            )
            for name in FOLDER_NAMES
        }

    def get_task_items(self, project_name, folder_id, sender=None):
        if project_name != "test" or folder_id is None:
            return []
        return [
            TaskItem(
                task_id=f"{folder_id}/{name}",
                name=name,
                label=name,
                task_type=name,
                task_type_order=0,
                parent_id=folder_id,
                tags=[],
                status="",
            )
            for name in TASK_NAMES
        ]

    def get_folder_type_items(self, project_name, sender=None):
        return []

    def get_task_type_items(self, project_name, sender=None):
        return []

    def set_selected_folder(self, folder_id: Optional[str]) -> None:
        self._selection.set_selected_folder(folder_id)

    def set_selected_task(self, task_id, task_name) -> None:
        self._selection.set_selected_task(task_id, task_name)

    def get_selected_folder_id(self) -> Optional[str]:
        return self._selection.get_selected_folder_id()

    def get_selected_task_id(self) -> Optional[str]:
        return self._selection.get_selected_task_id()

    def get_expected_selection_data(self):
        return self._expected.get_expected_selection_data()

    def set_expected_selection(self, project_name, folder_id, task_name):
        self._expected.set_expected_selection(
            project_name, folder_id, task_name
        )
        # The launcher window selects the project
        self._selection.set_selected_project(project_name)
        self._expected.expected_project_selected(project_name)

    def expected_folder_selected(self, folder_id) -> None:
        self._expected.expected_folder_selected(folder_id)

    def expected_task_selected(self, folder_id, task_name) -> None:
        self._expected.expected_task_selected(folder_id, task_name)

    def is_expected_selection_done(self) -> bool:
        data = self.get_expected_selection_data()
        return all(
            data[key]["selected"] for key in ("project", "folder", "task")
        )


@pytest.fixture
def page(qapp):
    controller = FakeController()
    parent = QtWidgets.QWidget()
    folders_widget = LauncherFoldersWidget(
        controller, parent, handle_expected_selection=True
    )
    tasks_widget = LauncherTasksWidget(
        controller, parent, handle_expected_selection=True
    )
    yield controller, folders_widget, tasks_widget
    parent.deleteLater()
    qapp.processEvents()


def go_to(qapp, controller, project_name, folder_id, task_name) -> None:
    controller.set_expected_selection(project_name, folder_id, task_name)
    end = time.time() + 5.0
    while not controller.is_expected_selection_done():
        if time.time() > end:
            raise AssertionError(
                "Expected selection did not finish:"
                f" {controller.get_expected_selection_data()}"
            )
        qapp.processEvents()
        time.sleep(0.005)


def test_task_of_same_name_in_other_folder_is_selected(qapp, page):
    controller, folders_widget, tasks_widget = page
    go_to(qapp, controller, "test", "sh020", "layout")

    go_to(qapp, controller, "test", "sh030", "layout")

    assert folders_widget.get_selected_folder_id() == "sh030"
    assert tasks_widget.get_selected_task_name() == "layout"
    assert controller.get_selected_task_id() == "sh030/layout"


def test_folder_without_task_clears_task(qapp, page):
    controller, folders_widget, tasks_widget = page
    go_to(qapp, controller, "test", "sh020", "layout")

    go_to(qapp, controller, "test", "sh030", None)

    assert folders_widget.get_selected_folder_id() == "sh030"
    assert tasks_widget.get_selected_task_name() is None
    assert controller.get_selected_task_id() is None


@pytest.mark.parametrize("project_name", ["test", "other"])
def test_project_without_folder_clears_folder(qapp, page, project_name):
    controller, folders_widget, tasks_widget = page
    go_to(qapp, controller, "test", "sh020", "layout")

    go_to(qapp, controller, project_name, None, None)

    assert folders_widget.get_selected_folder_id() is None
    assert tasks_widget.get_selected_task_name() is None
    assert controller.get_selected_folder_id() is None
    assert controller.get_selected_task_id() is None
