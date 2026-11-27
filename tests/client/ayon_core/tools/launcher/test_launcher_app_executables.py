"""Launcher hides applications without executable on this machine."""
from __future__ import annotations

import threading
import time

import pytest

from ayon_core.tools.launcher.abstract import ActionItem
from ayon_core.tools.launcher.models.actions import ActionsModel


class ApplicationsAddon:
    """Applications addon where only 'maya/2026' has executable."""
    def __init__(self, show_only_available=True):
        self.show_only_available = show_only_available
        self.request_started = threading.Event()
        self.release_request = threading.Event()
        self.release_request.set()
        self.requests = 0
        self.validated = []

    def get_application_items(self, project_name, task_id=None, **kwargs):
        self.requests += 1
        self.request_started.set()
        self.release_request.wait(5)
        return [
            {
                "full_name": app_name,
                "executables": {},
                "show_only_available": self.show_only_available,
            }
            for app_name in ("maya/2026", "nuke/17-1", "houdini/21")
        ]

    def validate_app_items_executable_paths(self, app_items):
        names = [app_item["full_name"] for app_item in app_items]
        self.validated.extend(names)
        return {name: name == "maya/2026" for name in names}


class Controller:
    def __init__(self, addon):
        self._addon = addon

    def get_addons_manager(self):
        return {"applications": self._addon}


def _action(identifier, addon_name="applications"):
    return ActionItem(
        action_type="webaction",
        identifier=identifier,
        order=0,
        suborder=0,
        label=identifier,
        variant_label=None,
        full_label=identifier,
        icon=None,
        addon_name=addon_name,
        addon_version="1.0.0",
        config_fields=[],
    )


ACTIONS = [
    _action("application.launch.nuke/17-1"),
    _action("application.launch.maya/2026"),
    _action("core.action", addon_name="core"),
    _action("application.launch-workfile.maya/2026"),
    _action("application.launch-workfile.nuke/17-1"),
]


def _filter(model, actions=ACTIONS):
    output = model._filter_app_executables("project", "task_id", actions)
    return [action.identifier for action in output]


@pytest.mark.unit
def test_applications_without_executable_are_hidden():
    addon = ApplicationsAddon()
    model = ActionsModel(Controller(addon))

    expected = [
        "application.launch.maya/2026",
        "core.action",
        "application.launch-workfile.maya/2026",
    ]
    assert _filter(model) == expected
    # Validity is reused for other selections in the project
    assert _filter(model) == expected
    assert sorted(addon.validated) == ["maya/2026", "nuke/17-1"]


@pytest.mark.unit
def test_nothing_is_validated_if_disabled():
    addon = ApplicationsAddon(show_only_available=False)
    model = ActionsModel(Controller(addon))

    assert _filter(model) == [action.identifier for action in ACTIONS]
    assert addon.validated == []


@pytest.mark.unit
def test_selection_during_first_request_is_filtered():
    addon = ApplicationsAddon()
    model = ActionsModel(Controller(addon))
    addon.release_request.clear()
    results = []
    first = threading.Thread(target=lambda: results.append(_filter(model)))
    first.start()
    addon.request_started.wait(5)
    second = threading.Thread(target=lambda: results.append(_filter(model)))
    second.start()
    # Second selection either waits for its own request or is done
    deadline = time.monotonic() + 5
    while second.is_alive() and addon.requests < 2:
        if time.monotonic() > deadline:
            break
        time.sleep(0.01)
    addon.release_request.set()
    first.join(5)
    second.join(5)

    assert results == [results[0], results[0]]
    assert "application.launch.nuke/17-1" not in results[0]
