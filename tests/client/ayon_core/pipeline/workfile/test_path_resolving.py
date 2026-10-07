"""Test workfile path resolving in the pipeline module."""
from __future__ import annotations

import os

import pytest

from ayon_core.pipeline.workfile.path_resolving import (
    get_next_workfile_version_path,
)

FILE_TEMPLATE = (
    "{project[code]}_{folder[name]}_{task[name]}"
    "_v{version:0>3}<_{comment}>.{ext}"
)
TEMPLATE_DATA = {
    "project": {"name": "project", "code": "prj"},
    "folder": {"name": "sh010"},
    "task": {"name": "anim"},
    # Values that should not affect the result
    "version": 1,
    "ext": "mb",
    "comment": "ignored",
}


def _create_workdir(tmp_path, name: str, *filenames: str):
    """Create directory with files, 'tmp_path' can be shared by tests."""
    workdir = tmp_path / name
    workdir.mkdir()
    for filename in filenames:
        (workdir / filename).write_text("")
    return workdir


def test_next_workfile_version_path(tmp_path):
    workdir = _create_workdir(
        tmp_path,
        "versions",
        "prj_sh010_anim_v001.ma",
        "prj_sh010_anim_v002_blocking.ma",
        "prj_sh010_anim_v003.ma",
        # Different extension and context are ignored
        "prj_sh010_anim_v007.mb",
        "prj_sh010_layout_v009.ma",
    )

    path, version, comment = get_next_workfile_version_path(
        str(workdir / "prj_sh010_anim_v003.ma"),
        FILE_TEMPLATE,
        TEMPLATE_DATA,
    )
    assert os.path.dirname(path) == str(workdir)
    assert os.path.basename(path) == "prj_sh010_anim_v004.ma"
    assert (version, comment) == (4, None)

    # Version is higher than the last version, comment is kept
    path, version, comment = get_next_workfile_version_path(
        str(workdir / "prj_sh010_anim_v002_blocking.ma"),
        FILE_TEMPLATE,
        TEMPLATE_DATA,
    )
    assert os.path.basename(path) == "prj_sh010_anim_v004_blocking.ma"
    assert (version, comment) == (4, "blocking")
    # Passed data are not changed
    assert TEMPLATE_DATA["version"] == 1


def test_next_workfile_version_path_unknown_version(tmp_path):
    workdir = _create_workdir(tmp_path, "custom", "custom_name.ma")
    with pytest.raises(ValueError):
        get_next_workfile_version_path(
            str(workdir / "custom_name.ma"), FILE_TEMPLATE, TEMPLATE_DATA
        )
