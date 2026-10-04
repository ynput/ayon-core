"""Tests for the Browser double click and space bar default actions."""

from __future__ import annotations

from typing import Any

import pytest

from ayon_core.tools.browser.abstract import ActionItem
from ayon_core.tools.browser.models import actions as actions_module
from ayon_core.tools.browser.models.actions import (
    LOADER_PLUGIN_ID,
    LoaderActionsModel,
    find_action_item_by_name,
)


def _action_item(
    identifier: str,
    label: str,
    group_label: str | None = None,
    order: int = 0,
    data: dict[str, Any] | None = None,
) -> ActionItem:
    return ActionItem(
        identifier,
        label=label,
        group_label=group_label,
        icon=None,
        tooltip=None,
        order=order,
        data=data,
        options=None,
    )


def _make_action_items() -> list[ActionItem]:
    return [
        _action_item("core.open-file", "h264", "Open file", order=30),
        _action_item("core.open-file", "exr", "Open file", order=30),
        _action_item(
            LOADER_PLUGIN_ID,
            "Load image (exr)",
            order=10,
            data={"loader": "LoadImage"},
        ),
        _action_item("core.copy-file", "Copy file path", order=20),
    ]


@pytest.mark.parametrize(
    "name, expected_label",
    [
        # Group label uses the first item in the context menu order
        ("Open file", "exr"),
        ("open FILE ", "exr"),
        ("Open file (h264)", "h264"),
        ("core.open-file", "exr"),
        ("Copy file path", "Copy file path"),
        ("Load image (exr)", "Load image (exr)"),
        ("LoadImage", "Load image (exr)"),
        ("Missing action", None),
        ("", None),
        # Internal identifier shared by all loader plugins
        (LOADER_PLUGIN_ID, None),
    ],
)
def test_find_action_item_by_name(
    name: str, expected_label: str | None
) -> None:
    item = find_action_item_by_name(_make_action_items(), name)
    label = None if item is None else item.label
    assert label == expected_label


DEFAULT_PROFILE = {
    "host_names": [],
    "task_types": [],
    "task_names": [],
    "product_base_types": [],
    "double_click_actions": [],
    "spacebar_actions": ["Open file"],
}
RENDER_PROFILE = {
    "host_names": ["maya"],
    "task_types": [],
    "task_names": [],
    "product_base_types": ["render"],
    "double_click_actions": ["Load image"],
    "spacebar_actions": [],
}


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> LoaderActionsModel:
    model = LoaderActionsModel(controller=None)
    contexts = {
        "v1": {
            "product": {"productBaseType": "render", "productType": "x"},
            "version": {"id": "v1", "taskId": "t1"},
        },
        "v2": {
            "product": {"productType": "model"},
            "version": {"id": "v2", "taskId": None},
        },
    }
    monkeypatch.setattr(
        model,
        "_contexts_for_versions",
        lambda _project_name, version_ids: (
            {
                version_id: contexts[version_id]
                for version_id in version_ids
                if version_id in contexts
            },
            {},
        ),
    )
    monkeypatch.setattr(
        actions_module.ayon_api,
        "get_tasks",
        lambda _project_name, task_ids: [
            {"id": task_id, "name": "lighting", "taskType": "Lighting"}
            for task_id in task_ids
        ],
    )
    monkeypatch.setattr(
        model,
        "_get_action_items",
        lambda *_args: _make_action_items(),
    )
    return model


def test_default_profile_spacebar_opens_file(
    model: LoaderActionsModel,
) -> None:
    profiles = [DEFAULT_PROFILE]

    action = model.get_default_action(
        "demo", "v1", "spacebar", profiles, None
    )
    assert action is not None
    assert action.names == ["Open file"]
    assert action.item is not None
    assert action.item.full_label == "Open file (exr)"

    # Double click is not set in the default profile
    assert model.get_default_action(
        "demo", "v1", "double_click", profiles, None
    ) is None


def test_more_specific_profile_is_used(model: LoaderActionsModel) -> None:
    profiles = [DEFAULT_PROFILE, RENDER_PROFILE]

    action = model.get_default_action(
        "demo", "v1", "double_click", profiles, "maya"
    )
    assert action is not None
    # The action is set but no available action item has that name
    assert action.names == ["Load image"]
    assert action.item is None
    assert model.get_default_action(
        "demo", "v1", "spacebar", profiles, "maya"
    ) is None

    # Other host and other product base type use the default profile
    for version_id, host_name in (("v1", "nuke"), ("v2", "maya")):
        action = model.get_default_action(
            "demo", version_id, "spacebar", profiles, host_name
        )
        assert action is not None
        assert action.names == ["Open file"]


@pytest.mark.parametrize(
    "names, expected_label",
    [
        (["Open file (exr)", "Open file", "Copy file path"], "exr"),
        (["Open file (mov)", "Open file", "Copy file path"], "exr"),
        (["Open file (mov)", "Copy file path", "Open file"], "Copy file path"),
        (["Open file (mov)", " "], None),
    ],
)
def test_actions_order_of_preference(
    model: LoaderActionsModel,
    names: list[str],
    expected_label: str | None,
) -> None:
    profile = dict(DEFAULT_PROFILE, spacebar_actions=names)
    action = model.get_default_action(
        "demo", "v1", "spacebar", [profile], None
    )
    assert action is not None
    label = None if action.item is None else action.item.label
    assert label == expected_label


def test_task_filters(model: LoaderActionsModel) -> None:
    profile = dict(
        DEFAULT_PROFILE, task_types=["Lighting"], task_names=["lighting"]
    )
    assert model.get_default_action(
        "demo", "v1", "spacebar", [profile], None
    ) is not None
    # Version without a task does not match a task specific profile
    assert model.get_default_action(
        "demo", "v2", "spacebar", [profile], None
    ) is None


def test_unknown_version_has_no_default_action(
    model: LoaderActionsModel,
) -> None:
    assert model.get_default_action(
        "demo", "missing", "spacebar", [DEFAULT_PROFILE], None
    ) is None
