"""Hidden files in a work dir must not be treated as workfiles.

On network shares without Apple metadata support macOS writes an AppleDouble
'._<name>' file next to every file, and Finder may add '.DS_Store'.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

from ayon_core.host import IWorkfileHost
from ayon_core.host.interfaces import workfiles as workfiles_interface
from ayon_core.pipeline.workfile.path_resolving import (
    get_last_workfile_with_version,
)

FILE_TEMPLATE = (
    "{project[code]}_{folder[name]}_{task[name]}"
    "_v{version:0>3}<_{comment}>.{ext}"
)
TEMPLATE_DATA = {
    "project": {"code": "ab"},
    "folder": {"name": "sh010"},
    "task": {"name": "edit"},
}


class _Workdir(str):
    """Stand-in for the filled workdir template result."""
    rootless = "{root[work]}/ab/sh010/work/edit"


def _create_workdir(tmp_path, *filenames):
    # Own folder per test, 'tmp_path' may be shared by test plugins
    workdir = Path(tempfile.mkdtemp(dir=tmp_path))
    for filename in filenames:
        (workdir / filename).write_bytes(b"")
    return workdir


def test_last_workfile_skips_hidden_files(tmp_path):
    # Template starting with an optional key also matches '._' prefix
    file_template = "<{comment}_>{task[name]}_v{version:0>3}.{ext}"
    workdir = _create_workdir(
        tmp_path, "edit_v002.drp", "._edit_v002.drp", ".DS_Store"
    )
    # AppleDouble file is written right after the workfile
    os.utime(workdir / "edit_v002.drp", (1_000_000_000, 1_000_000_000))
    os.utime(workdir / "._edit_v002.drp", (2_000_000_000, 2_000_000_000))

    filepath, version = get_last_workfile_with_version(
        str(workdir), file_template, TEMPLATE_DATA, {"drp"}
    )

    assert version == 2
    assert os.path.basename(filepath) == "edit_v002.drp"


def test_list_workfiles_skips_hidden_files(tmp_path, mocker):
    workdir = _create_workdir(
        tmp_path,
        "ab_sh010_edit_v001.drp",
        "._ab_sh010_edit_v001.drp",
        ".DS_Store",
    )
    anatomy = Mock()
    anatomy.get_template_item.return_value = FILE_TEMPLATE
    mocker.patch.object(
        workfiles_interface,
        "get_list_workfiles_context",
        return_value=Mock(
            workfile_entities=[],
            anatomy=anatomy,
            template_key="default",
        ),
    )
    mocker.patch(
        "ayon_core.pipeline.template_data.get_template_data",
        return_value=TEMPLATE_DATA,
    )
    mocker.patch(
        "ayon_core.pipeline.workfile.path_resolving"
        ".get_workdir_with_workdir_data",
        return_value=_Workdir(workdir),
    )
    host = Mock()
    host.name = "resolve"
    host.get_workfile_extensions.return_value = [".drp"]

    items = IWorkfileHost.list_workfiles(host, "ab", {}, {})

    assert [os.path.basename(item.filepath) for item in items] == [
        "ab_sh010_edit_v001.drp"
    ]
    assert items[0].version == 1
