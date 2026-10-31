"""Preferences of the Launcher stored on this machine."""
from __future__ import annotations

import pytest

from ayon_core.lib import JSONSettingRegistry, get_launcher_local_dir
from ayon_core.tools.launcher.control import BaseLauncherController


@pytest.fixture
def local_dir(tmp_path_factory, monkeypatch) -> str:
    # 'tmp_path' of pytest-ayon is shared by the whole session
    tmp_path = tmp_path_factory.mktemp("local_dir")
    monkeypatch.setenv("AYON_LAUNCHER_LOCAL_DIR", str(tmp_path))
    return str(tmp_path)


@pytest.mark.unit
def test_grouped_hosts_of_previous_versions_are_used(local_dir):
    # What the Launcher stored before it used local preferences
    registry = JSONSettingRegistry("launcher", get_launcher_local_dir("tools"))
    registry.set_item("grouped_hosts", '["maya", null]')

    controller = BaseLauncherController()
    assert controller.get_grouped_host_names() == ["maya", None]

    controller.set_grouped_host_names(["nuke"])
    assert BaseLauncherController().get_grouped_host_names() == ["nuke"]
    # Previous versions read what is stored now
    registry = JSONSettingRegistry("launcher", get_launcher_local_dir("tools"))
    assert registry.get_item("grouped_hosts") == '["nuke"]'
