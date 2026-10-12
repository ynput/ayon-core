"""Tests for workfiles tool model."""

from __future__ import annotations

import os
from unittest.mock import Mock, create_autospec

import pytest

from ayon_core.host import IWorkfileHost
from ayon_core.tools.workfiles.models import workfiles

PROJECT_NAME = "demo"
FOLDER_ENTITY = {"id": "folder-id", "path": "/shots/sh010"}
TASK_ENTITY = {"id": "task-id", "name": "animation"}


@pytest.fixture
def host():
    # Autospec validates used arguments against 'IWorkfileHost' signatures
    return create_autospec(IWorkfileHost, instance=True)


@pytest.fixture
def controller():
    controller = Mock()
    controller.is_host_valid.return_value = True
    controller.get_workfile_extensions.return_value = [".ma"]
    controller.get_current_project_name.return_value = PROJECT_NAME
    controller.get_folder_entity.return_value = FOLDER_ENTITY
    controller.get_task_entity.return_value = TASK_ENTITY
    return controller


@pytest.fixture
def model(monkeypatch, host, controller):
    monkeypatch.setattr(
        workfiles.ayon_api, "get_workfiles_info", Mock(return_value=[])
    )
    return workfiles.WorkfilesModel(host, controller)


def _duplicate_workfile(model, tmp_path):
    workdir = str(tmp_path / "work")
    model.duplicate_workfile(
        FOLDER_ENTITY["id"],
        TASK_ENTITY["id"],
        str(tmp_path / "work" / "sh010_animation_v001.ma"),
        "{root[work]}/demo/shots/sh010/work/animation",
        workdir,
        "sh010_animation_v002.ma",
        version=2,
        comment=None,
        description="Duplicated",
    )
    return workdir


def test_duplicate_workfile_does_not_open_workfile(
    model, host, controller, tmp_path
):
    workdir = _duplicate_workfile(model, tmp_path)

    host.copy_workfile.assert_called_once()
    args, kwargs = host.copy_workfile.call_args
    assert args == (
        str(tmp_path / "work" / "sh010_animation_v001.ma"),
        os.path.join(workdir, "sh010_animation_v002.ma"),
        FOLDER_ENTITY,
        TASK_ENTITY,
    )
    assert kwargs["version"] == 2
    assert kwargs["description"] == "Duplicated"
    # Host would open the workfile by default
    assert kwargs["open_workfile"] is False

    host.open_workfile.assert_not_called()
    host.open_workfile_with_context.assert_not_called()
    controller.emit_event.assert_called_with(
        "workfile_duplicate.finished", {"failed": False}, "workfiles"
    )


def test_duplicate_workfile_reports_failure(
    model, host, controller, tmp_path
):
    host.copy_workfile.side_effect = OSError("Copy failed")

    _duplicate_workfile(model, tmp_path)

    controller.emit_event.assert_called_with(
        "workfile_duplicate.finished", {"failed": True}, "workfiles"
    )
