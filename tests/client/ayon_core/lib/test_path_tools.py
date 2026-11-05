"""Tests of path tools."""
from unittest import mock

import pytest

from ayon_core.lib import path_tools


@pytest.fixture
def workfile(tmp_path):
    filepath = tmp_path / "workfile_v001.ma"
    filepath.write_text("")
    return filepath


def _open_in_file_browser(path, platform_name):
    """Call 'open_in_file_browser' with mocked platform and executables.

    Returns:
        tuple[list, list]: Arguments passed to 'subprocess.Popen' and to
            'os.startfile'.

    """
    with mock.patch.object(
        path_tools.platform, "system", return_value=platform_name
    ), mock.patch.object(
        path_tools.subprocess, "Popen"
    ) as popen_mock, mock.patch.object(
        path_tools.os, "startfile", create=True
    ) as startfile_mock:
        path_tools.open_in_file_browser(str(path))
    return (
        [call.args[0] for call in popen_mock.call_args_list],
        [call.args[0] for call in startfile_mock.call_args_list],
    )


def test_open_in_file_browser_windows(workfile):
    # File is selected in explorer
    popen_args, startfile_args = _open_in_file_browser(workfile, "Windows")
    assert popen_args == [["explorer", "/select,", str(workfile)]]
    assert startfile_args == []

    # Directory is opened
    popen_args, startfile_args = _open_in_file_browser(
        workfile.parent, "Windows"
    )
    assert popen_args == []
    assert startfile_args == [str(workfile.parent)]


def test_open_in_file_browser_macos(workfile):
    # File is revealed in Finder
    popen_args, _ = _open_in_file_browser(workfile, "Darwin")
    assert popen_args == [["open", "-R", str(workfile)]]

    # Directory is opened
    popen_args, _ = _open_in_file_browser(workfile.parent, "Darwin")
    assert popen_args == [["open", str(workfile.parent)]]


def test_open_in_file_browser_linux(workfile):
    # File cannot be selected, so its directory is opened
    for path in (workfile, workfile.parent):
        popen_args, _ = _open_in_file_browser(path, "Linux")
        assert popen_args == [["xdg-open", str(workfile.parent)]]


def test_open_in_file_browser_unknown_platform(workfile):
    with pytest.raises(RuntimeError):
        _open_in_file_browser(workfile, "Unknown")
