"""'save_next_version' saves with an extension the host can save to.

Houdini Apprentice can open a commercial '.hip' but saves it as '.hipnc'.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from ayon_core.host import IWorkfileHost, WorkfileInfo
from ayon_core.host.interfaces import SaveWorkfileOptionalData
from ayon_core.lib import StringTemplate
from ayon_core.pipeline.workfile import utils as workfile_utils

FILE_TEMPLATE = "{folder[name]}_{task[name]}_v{version:0>3}.{ext}"
ROOTLESS_WORKDIR = "{root[work]}/test/sh010/work/fx"


class _Workdir(str):
    """Stand-in for the filled workdir template result."""
    rootless = ROOTLESS_WORKDIR


@pytest.mark.parametrize(
    ("current_filename", "workfile_filenames", "expected_filename"),
    [
        # Opened a '.hip' saved with a commercial license
        ("sh010_fx_v003.hip", ["sh010_fx_v003.hip"], "sh010_fx_v004.hipnc"),
        # Unsaved scene, last workfile is a '.hip'
        (None, ["sh010_fx_v003.hip"], "sh010_fx_v004.hipnc"),
        # Unsaved scene, no workfiles yet
        (None, [], "sh010_fx_v001.hipnc"),
    ],
)
def test_save_next_version_uses_save_extension(
    tmp_path, mocker, current_filename, workfile_filenames, expected_filename
):
    workdir = str(tmp_path)
    workfiles = [
        WorkfileInfo.new(
            os.path.join(workdir, filename),
            f"{ROOTLESS_WORKDIR}/{filename}",
            version=3,
            comment=None,
            available=True,
            workfile_entity={},
        )
        for filename in workfile_filenames
    ]
    current_path = None
    if current_filename:
        current_path = os.path.join(workdir, current_filename)

    host = mock.MagicMock(spec=IWorkfileHost)
    host.name = "houdini"
    host.get_current_context.return_value = {
        "project_name": "test",
        "folder_path": "/sh010",
        "task_name": "fx",
    }
    host.get_current_workfile.return_value = current_path
    host.get_workfile_extensions.return_value = [".hipnc", ".hip", ".hiplc"]
    host.get_workfile_save_extensions.return_value = [".hipnc"]
    host.list_workfiles.return_value = workfiles
    mocker.patch(
        "ayon_core.pipeline.context_tools.registered_host",
        return_value=host,
    )
    # Avoid server calls
    mocker.patch.object(
        workfile_utils.ayon_api,
        "get_folder_by_path",
        return_value={"id": "folder-1", "name": "sh010"},
    )
    mocker.patch.object(
        workfile_utils.ayon_api,
        "get_task_by_name",
        return_value={"id": "task-1", "name": "fx", "taskType": "FX"},
    )
    mocker.patch.object(
        workfile_utils, "get_workfile_template_key", return_value="default"
    )
    mocker.patch.object(
        workfile_utils,
        "get_template_data",
        return_value={"folder": {"name": "sh010"}, "task": {"name": "fx"}},
    )
    mocker.patch.object(
        workfile_utils, "get_workdir", return_value=_Workdir(workdir)
    )
    mocker.patch.object(
        workfile_utils, "get_versioning_start", return_value=1
    )
    anatomy = mock.Mock()
    anatomy.get_template_item.return_value = StringTemplate(FILE_TEMPLATE)
    prepared_data = SaveWorkfileOptionalData(
        project_entity={"name": "test"},
        anatomy=anatomy,
        project_settings={},
    )

    workfile_utils.save_next_version(prepared_data=prepared_data)

    host.save_workfile_with_context.assert_called_once()
    filepath = host.save_workfile_with_context.call_args.args[0]
    assert filepath == os.path.join(workdir, expected_filename)
    assert prepared_data.rootless_path == (
        f"{ROOTLESS_WORKDIR}/{expected_filename}"
    )
