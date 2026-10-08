"""Tests of workfile actions model of workfiles tool."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from ayon_core.host import IWorkfileHost, WorkfileInfo
from ayon_core.pipeline.actions import WorkfileActionResult
from ayon_core.tools.workfiles.abstract import (
    ActionItem,
    ActionSelectionData,
)
from ayon_core.tools.workfiles.control import BaseWorkfileController

PROJECT_NAME = "test_project"
FOLDER_ENTITY = {"id": "folder-1", "path": "/shots/sh010"}
TASK_ENTITY = {
    "id": "task-1",
    "folderId": "folder-1",
    "name": "comp",
    "taskType": "Compositing",
}
ROOTLESS_PATH = "{root[work]}/sh010/work/comp/sh010_comp_v001.ma"


class _FakeAddonsManager:
    addons = []


@pytest.fixture
def controller(tmp_path):
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_workfile_extensions.return_value = [".ma"]

    controller = BaseWorkfileController(host=host)
    controller._current_project_name = PROJECT_NAME
    # Avoid server calls
    controller._project_anatomy = mock.Mock()
    controller._settings_model._settings[PROJECT_NAME] = {"core": {}}
    controller.get_project_entity = lambda *_: {"name": PROJECT_NAME}
    controller.get_folder_entity = lambda *_: FOLDER_ENTITY
    controller.get_task_entity = lambda *_: TASK_ENTITY
    controller.get_workfile_entities = lambda *_: [{"id": "workfile-1"}]
    controller._actions_model._context._addons_manager = _FakeAddonsManager()

    workfile_path = tmp_path / "sh010_comp_v001.ma"
    workfile_path.write_text("")
    workfiles_model = controller._workfiles_model
    workfiles_model._workdir_by_context = {
        "folder-1": {"task-1": str(tmp_path)}
    }
    workfiles_model._workarea_file_items_mapping = {
        "task-1": {
            ROOTLESS_PATH: WorkfileInfo.new(
                str(workfile_path),
                ROOTLESS_PATH,
                version=1,
                comment=None,
                available=True,
                workfile_entity={"id": "workfile-1", "attrib": {}},
            )
        }
    }
    controller.set_selected_folder("folder-1")
    controller.set_selected_task("task-1", "comp")
    controller.set_selected_workfile_path(
        ROOTLESS_PATH, str(workfile_path), "workfile-1"
    )
    return controller


def test_selection_and_action_items(controller):
    selection = controller.get_workfile_action_selection(False)
    assert selection.rootless_path == ROOTLESS_PATH
    assert selection.workfile_entity_id == "workfile-1"
    assert selection == controller.get_workfile_action_selection(False)

    items = controller.get_workfile_action_items(selection)
    assert [item.identifier for item in items] == [
        "core.increment-and-open",
        "core.duplicate-workfile",
        "core.explore-here",
    ]

    # Selection related only to the work area
    area_selection = controller.get_workfile_action_selection(
        False, with_workfile=False
    )
    assert area_selection.filepath is None
    assert area_selection != selection
    items = controller.get_workfile_action_items(area_selection)
    assert [item.identifier for item in items] == ["core.explore-here"]

    # Published workfile is not selected
    published_selection = controller.get_workfile_action_selection(True)
    assert published_selection == ActionSelectionData(
        published=True, folder_id="folder-1", task_id="task-1"
    )
    assert controller.get_workfile_action_items(published_selection) == []


def test_action_items_are_converted_for_ui(controller):
    selection = controller.get_workfile_action_selection(False)
    items = controller.get_workfile_action_items(selection)
    assert all(isinstance(item, ActionItem) for item in items)

    quick_actions = {item.identifier: item.quick_action for item in items}
    assert quick_actions == {
        "core.explore-here": True,
        "core.increment-and-open": True,
        "core.duplicate-workfile": False,
    }
    # Items can be converted to data and back
    assert [ActionItem.from_data(item.to_data()) for item in items] == items


def test_action_items_are_cached(controller):
    selection = controller.get_workfile_action_selection(False)
    assert controller.get_cached_workfile_action_items(selection) is None

    context = controller._actions_model._context
    with mock.patch.object(
        context, "get_action_items", wraps=context.get_action_items
    ) as get_items_mock:
        items = controller.get_workfile_action_items(selection)
        assert items
        assert controller.get_cached_workfile_action_items(selection) == items
        assert controller.get_workfile_action_items(selection) == items
        assert get_items_mock.call_count == 1

        # Available actions might be different after an action
        with mock.patch("subprocess.Popen"), mock.patch(
            "os.startfile", create=True
        ):
            controller.trigger_workfile_action(
                "core.explore-here", selection, None, {}
            )
        assert controller.get_cached_workfile_action_items(selection) is None
        assert controller.get_workfile_action_items(selection) == items
        assert get_items_mock.call_count == 2

    # Reset of the model does clear the cache too
    controller._actions_model.reset()
    assert controller.get_cached_workfile_action_items(selection) is None


def test_selection_passes_cached_data_to_plugins(controller):
    selection_data = controller.get_workfile_action_selection(False)
    selection = controller._actions_model._create_selection(selection_data)

    assert selection.is_workarea()
    assert selection.has_workfile()
    assert selection.workfile_info.version == 1
    assert selection.get_folder_entity() == FOLDER_ENTITY
    assert selection.get_task_entity() == TASK_ENTITY
    assert selection.get_workfile_entity() == {"id": "workfile-1"}
    assert selection.get_workdir() == os.path.dirname(selection_data.filepath)


def test_trigger_action_emits_events(controller):
    events = []

    # Event system keeps only weak reference to the callback
    def _on_event(event):
        events.append(event)

    for topic in ("workfile_action.started", "workfile_action.finished"):
        controller.register_event_callback(topic, _on_event)

    selection = controller.get_workfile_action_selection(False)
    with mock.patch("subprocess.Popen") as popen, mock.patch(
        "os.startfile", create=True
    ) as startfile:
        controller.trigger_workfile_action(
            "core.explore-here", selection, None, {}
        )
    assert popen.called or startfile.called

    assert [event.topic for event in events] == [
        "workfile_action.started", "workfile_action.finished"
    ]
    finished_event = events[-1]
    assert finished_event["crashed"] is False
    assert finished_event["result"] == WorkfileActionResult()
    # Events contain only data that can be serialized
    assert finished_event["selection"] == selection.to_data()
    assert ActionSelectionData.from_data(
        finished_event["selection"]
    ) == selection

    # Unknown plugin does not crash the tool
    events.clear()
    controller.trigger_workfile_action("unknown", selection, None, {})
    assert events[-1]["crashed"] is True
    assert events[-1]["result"] is None
