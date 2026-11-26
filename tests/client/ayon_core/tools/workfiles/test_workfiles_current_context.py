"""Tests of current context tracking in workfiles tool controller."""
from __future__ import annotations

from unittest import mock

import pytest

from ayon_core.host import IWorkfileHost
from ayon_core.lib.events import emit_event
from ayon_core.tools.common_models import hierarchy
from ayon_core.tools.workfiles.control import BaseWorkfileController

PROJECT_NAME = "test_project"


def _rest_folder(folder_id, path):
    return {
        "id": folder_id,
        "parentId": None,
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "label": None,
        "folderType": "Shot",
        "status": "open",
    }


class _FakeEventHub:
    def is_connected(self):
        return False

    def add_callbacks(self, callbacks, *, connect=True):
        pass


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        hierarchy, "_SHARED_FOLDERS_CACHE", hierarchy._SharedFoldersCache()
    )
    monkeypatch.setattr(hierarchy, "get_event_hub", _FakeEventHub)
    monkeypatch.setattr(
        hierarchy.ayon_api,
        "get_rest_folders",
        mock.Mock(return_value=[
            _rest_folder("folder-1", "shots/sh010"),
            _rest_folder("folder-2", "shots/sh020"),
        ]),
    )
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_current_context = mock.Mock()
    controller = BaseWorkfileController(host=host)
    controller._current_project_name = PROJECT_NAME
    controller._current_folder_path = "/shots/sh010"
    controller._current_folder_id = "folder-1"
    controller._current_task_name = "comp"
    # Folders are cached when the folders widget shows them
    controller.get_folder_items(PROJECT_NAME)
    return controller


def test_current_context_updates_on_context_change(controller, monkeypatch):
    # Folder id is resolved from cached folders, without server requests
    for attr in ("get_rest_folders", "get_folders"):
        monkeypatch.setattr(
            hierarchy.ayon_api,
            attr,
            mock.Mock(side_effect=AssertionError("Server was queried")),
        )

    host = controller._host
    new_context = {
        "project_name": PROJECT_NAME,
        "folder_path": "/shots/sh020",
        "task_name": "lighting",
    }
    host.get_current_context.return_value = new_context

    # Host is not asked for context without context change event
    assert controller.get_current_folder_id() == "folder-1"
    assert controller.get_current_task_name() == "comp"
    host.get_current_context.assert_not_called()

    # Save As switched context of the host while the tool stayed open
    emit_event("taskChanged", new_context)

    assert controller.get_current_folder_id() == "folder-2"
    assert controller.get_current_task_name() == "lighting"
    host.get_current_context.assert_called_once()
