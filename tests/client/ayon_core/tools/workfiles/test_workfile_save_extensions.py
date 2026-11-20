"""Save As offers the host's save extensions, not every openable one."""
from __future__ import annotations

from unittest import mock

import pytest

from ayon_core.host import IWorkfileHost
from ayon_core.tools.workfiles.control import BaseWorkfileController

FOLDER_ENTITY = {"id": "folder-1", "path": "/shots/sh010"}
TASK_ENTITY = {"id": "task-1", "name": "comp", "taskType": "Compositing"}


def test_save_extensions_default_to_workfile_extensions():
    host = mock.Mock()
    host.get_workfile_extensions.return_value = [".ma", ".mb"]

    extensions = IWorkfileHost.get_workfile_save_extensions(host)

    assert extensions == [".ma", ".mb"]


@pytest.mark.parametrize(
    ("current_workfile", "expected_ext"),
    [
        (None, ".ma"),
        ("C:/work/sh010_comp_v001.mb", ".mb"),
        ("C:/work/sh010_comp_v001.fbx", ".ma"),
    ],
)
def test_save_as_data_uses_save_extensions(current_workfile, expected_ext):
    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "testhost"
    host.get_workfile_extensions.return_value = [".ma", ".mb", ".fbx"]
    host.get_workfile_save_extensions.return_value = [".ma", ".mb"]
    host.get_current_workfile.return_value = current_workfile

    controller = BaseWorkfileController(host=host)
    # Avoid server calls
    controller._project_anatomy = mock.MagicMock()
    controller.get_folder_entity = lambda *_: FOLDER_ENTITY
    controller.get_task_entity = lambda *_: TASK_ENTITY
    model = controller._workfiles_model
    model._prepare_fill_data = lambda *_: {}
    model._get_template_key = lambda *_: "default"
    model._get_workdir = lambda *_: mock.Mock(rootless="{root[work]}/sh010")
    model.get_workarea_file_items = lambda *_: []
    model._get_last_workfile_version = lambda *_: 1

    data = model.get_workarea_save_as_data("folder-1", "task-1")

    assert data["extensions"] == [".ma", ".mb"]
    assert data["ext"] == expected_ext
