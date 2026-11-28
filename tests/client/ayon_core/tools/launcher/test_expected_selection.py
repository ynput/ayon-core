"""Tests for the selection the launcher UI is asked to navigate to."""

from __future__ import annotations

import pytest

from ayon_core.tools.launcher.models.expected_selection import (
    LauncherExpectedSelection,
)


class FakeController:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit_event(self, topic, data=None, source=None) -> None:
        self.events.append((topic, data))


@pytest.fixture
def controller() -> FakeController:
    return FakeController()


@pytest.fixture
def expected(controller) -> LauncherExpectedSelection:
    model = LauncherExpectedSelection(controller)
    model.set_expected_selection("project", "folder", "task", "workfile")
    return model


def current_parts(model: LauncherExpectedSelection) -> list[str]:
    return [
        name
        for name, data in model.get_expected_selection_data().items()
        if data["current"]
    ]


def test_parts_become_current_one_after_the_other(expected):
    assert current_parts(expected) == ["project"]

    assert expected.expected_project_selected("project")
    assert current_parts(expected) == ["folder"]

    assert expected.expected_folder_selected("folder")
    assert current_parts(expected) == ["task"]

    assert expected.expected_task_selected("folder", "task")
    assert current_parts(expected) == ["workfile"]

    assert expected.expected_workfile_selected("workfile")
    assert current_parts(expected) == []


def test_every_step_is_announced(controller, expected):
    expected.expected_project_selected("project")

    topics = [topic for topic, _data in controller.events]
    assert topics == ["expected_selection_changed"] * 2
    assert controller.events[-1][1]["project"]["selected"]


def test_selecting_something_else_does_not_confirm_a_step(expected):
    assert not expected.expected_project_selected("other")
    assert current_parts(expected) == ["project"]

    expected.expected_project_selected("project")
    assert not expected.expected_folder_selected("other")
    assert current_parts(expected) == ["folder"]


def test_task_is_only_confirmed_for_the_expected_folder(expected):
    expected.expected_project_selected("project")
    expected.expected_folder_selected("folder")

    assert not expected.expected_task_selected("other", "task")
    assert current_parts(expected) == ["task"]


def test_no_workfile_is_confirmed_as_none(controller):
    model = LauncherExpectedSelection(controller)
    model.set_expected_selection("project", "folder", "task")
    model.expected_project_selected("project")
    model.expected_folder_selected("folder")
    model.expected_task_selected("folder", "task")

    assert current_parts(model) == ["workfile"]
    assert model.expected_workfile_selected(None)
    assert current_parts(model) == []


def test_new_expectation_starts_over(expected):
    expected.expected_project_selected("project")
    expected.expected_folder_selected("folder")

    expected.set_expected_selection("project", "other_folder")

    assert current_parts(expected) == ["project"]
    data = expected.get_expected_selection_data()
    assert data["folder"]["id"] == "other_folder"
    assert not data["workfile"]["selected"]
