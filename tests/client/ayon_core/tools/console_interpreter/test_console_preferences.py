"""Preferences of the console interpreter stored on this machine."""
from __future__ import annotations

import os

import pytest

from ayon_core.lib import JSONSettingRegistry, get_launcher_local_dir
from ayon_core.tools.console_interpreter.control import (
    InterpreterController,
)


@pytest.fixture
def local_dir(tmp_path_factory, monkeypatch) -> str:
    # 'tmp_path' of pytest-ayon is shared by the whole session
    tmp_path = tmp_path_factory.mktemp("local_dir")
    monkeypatch.setenv("AYON_LAUNCHER_LOCAL_DIR", str(tmp_path))
    return str(tmp_path)


@pytest.mark.unit
def test_registry_of_previous_versions_is_copied(local_dir):
    # Previous versions stored it in the root of the local directory
    registry = JSONSettingRegistry("unreal", get_launcher_local_dir())
    registry.set_item("width", 800)
    registry.set_item("height", 600)
    registry.set_item("tabs", [{"name": "Main", "code": "print(1)"}])

    controller = InterpreterController(name="unreal")
    config = controller.get_config()
    assert (config.width, config.height) == (800, 600)
    assert [(tab.name, tab.code) for tab in config.tabs] == [
        ("Main", "print(1)")
    ]

    controller.save_config(1000, 700, [100, 200], [])
    assert os.path.exists(
        os.path.join(local_dir, "tools", "unreal.json")
    )
    # Not copied again, and the previous registry is left as it was
    config = InterpreterController(name="unreal").get_config()
    assert (config.width, config.height) == (1000, 700)
    registry = JSONSettingRegistry("unreal", get_launcher_local_dir())
    assert registry.get_item("width") == 800


@pytest.mark.unit
def test_config_without_previous_registry(local_dir):
    config = InterpreterController().get_config()
    assert (config.width, config.height) == (None, None)
    assert config.tabs == []
    assert not os.path.exists(os.path.join(local_dir, "tools"))
