"""Collectors reuse data cached by CreateContext instead of server queries."""
from __future__ import annotations

import collections
import copy
from typing import Any
from unittest.mock import patch

import pyblish.api
import pytest

from ayon_core.pipeline import PublishError
from ayon_core.pipeline.create import CreateContext
from ayon_core.plugins.publish.collect_anatomy_instance_data import (
    CollectAnatomyInstanceData,
)
from ayon_core.plugins.publish.collect_context_entities import (
    CollectContextEntities,
)
from ayon_core.plugins.publish.collect_hierarchy import CollectHierarchy
from ayon_core.plugins.publish.collect_instance_entities import (
    CollectInstanceEntities,
)
from ayon_core.plugins.publish.collect_settings import CollectSettings

PROJECT_NAME = "project"
CONTEXT_FOLDER_PATH = "/shots/sh010"
CONTEXT_TASK_NAME = "comp"
MISSING_FOLDER_PATH = "/shots/sh999"
TASK_NAMES_BY_FOLDER_PATH = {
    "/shots/sh010": ["comp"],
    "/shots/sh020": ["comp", "anim"],
}
PROJECT_SETTINGS = {"core": {"value": 1}}


def _folder_entity(folder_path: str) -> dict[str, Any]:
    return {
        "id": f"id{folder_path}",
        "path": folder_path,
        "name": folder_path.rsplit("/", 1)[-1],
        "attrib": {
            "frameStart": 1001,
            "frameEnd": 1010,
            "handleStart": 0,
            "handleEnd": 0,
            "fps": 25.0,
        },
    }


def _task_entity(folder_path: str, task_name: str) -> dict[str, Any]:
    return {
        "id": f"id{folder_path}/{task_name}",
        "name": task_name,
        "folderId": f"id{folder_path}",
        "taskType": "Compositing",
        "attrib": {"fps": 25.0},
    }


class _FakeAnatomy:
    def __init__(self, project_name=None, project_entity=None):
        assert project_entity is not None
        self.project_name = project_name


class _Host:
    name = "test"

    def get_current_context(self):
        return {
            "project_name": PROJECT_NAME,
            "folder_path": CONTEXT_FOLDER_PATH,
            "task_name": CONTEXT_TASK_NAME,
        }

    def get_context_data(self):
        return {}

    def update_context_data(self, data, changes):
        pass

    def get_context_title(self):
        return "Test"


@pytest.fixture
def server_calls():
    """Fake AYON server returning entities and counting calls."""
    calls = collections.Counter()
    folder_entities = {
        folder_path: _folder_entity(folder_path)
        for folder_path in TASK_NAMES_BY_FOLDER_PATH
    }
    task_entities = [
        _task_entity(folder_path, task_name)
        for folder_path, task_names in TASK_NAMES_BY_FOLDER_PATH.items()
        for task_name in task_names
    ]

    def get_project(project_name, *args, **kwargs):
        calls["get_project"] += 1
        return {"name": project_name, "code": "prj", "taskTypes": []}

    def get_folders(project_name, folder_paths=None, **kwargs):
        calls["get_folders"] += 1
        for folder_path in folder_paths:
            if folder_path in folder_entities:
                yield copy.deepcopy(folder_entities[folder_path])

    def get_folder_by_path(project_name, folder_path, **kwargs):
        calls["get_folder_by_path"] += 1
        return copy.deepcopy(folder_entities.get(folder_path))

    def get_tasks(
        project_name, folder_ids=None, task_names=None, **kwargs
    ):
        calls["get_tasks"] += 1
        for task_entity in task_entities:
            if task_entity["folderId"] not in folder_ids:
                continue
            if task_names and task_entity["name"] not in task_names:
                continue
            yield copy.deepcopy(task_entity)

    def get_task_by_name(project_name, folder_id, task_name, **kwargs):
        calls["get_task_by_name"] += 1
        return next(get_tasks(project_name, [folder_id], [task_name]), None)

    def get_project_settings(project_name):
        calls["get_project_settings"] += 1
        return copy.deepcopy(PROJECT_SETTINGS)

    plugins = "ayon_core.plugins.publish"
    with (
        patch("ayon_api.get_project", get_project),
        patch("ayon_api.get_folders", get_folders),
        patch("ayon_api.get_folder_by_path", get_folder_by_path),
        patch("ayon_api.get_tasks", get_tasks),
        patch("ayon_api.get_task_by_name", get_task_by_name),
        patch(
            "ayon_core.pipeline.create.context.get_project_settings",
            get_project_settings,
        ),
        patch(
            f"{plugins}.collect_settings.get_project_settings",
            get_project_settings,
        ),
        patch("ayon_core.pipeline.create.context.Anatomy", _FakeAnatomy),
        patch(f"{plugins}.collect_context_entities.Anatomy", _FakeAnatomy),
    ):
        yield calls


def _create_create_context() -> CreateContext:
    """CreateContext with cache filled like after a Publisher reset."""
    create_context = CreateContext(_Host(), reset=False)
    create_context.reset_current_context()
    create_context.get_current_project_settings()
    create_context.get_current_project_entity()
    create_context.get_task_entities({
        folder_path: set(task_names)
        for folder_path, task_names in TASK_NAMES_BY_FOLDER_PATH.items()
    })
    create_context.get_folder_entities([MISSING_FOLDER_PATH])
    return create_context


def _create_publish_context(
    create_context: CreateContext | None,
) -> pyblish.api.Context:
    context = pyblish.api.Context()
    context.data.update({
        "projectName": PROJECT_NAME,
        "folderPath": CONTEXT_FOLDER_PATH,
        "task": CONTEXT_TASK_NAME,
    })
    if create_context is not None:
        context.data["create_context"] = create_context

    for idx, (folder_path, task_name) in enumerate((
        (CONTEXT_FOLDER_PATH, CONTEXT_TASK_NAME),
        ("/shots/sh020", "anim"),
        ("/shots/sh020", "missing"),
        (MISSING_FOLDER_PATH, "comp"),
    )):
        instance = context.create_instance(f"instance{idx}")
        instance.data.update({
            "folderPath": folder_path,
            "task": task_name,
            "productName": f"product{idx}",
            "productType": "shot",
            "families": ["shot"],
            "heroTrack": True,
            "parents": [{"entity_name": "shots", "folder_type": "Folder"}],
            # Shot attributes are collected only for new folders
            "frameStart": 1001,
        })
    return context


def _collect(context: pyblish.api.Context) -> None:
    for plugin in (
        CollectSettings,
        CollectContextEntities,
        CollectInstanceEntities,
        CollectHierarchy,
    ):
        plugin().process(context)

    # Remove entities filled by 'CollectInstanceEntities' to test
    #   'CollectAnatomyInstanceData' fills them the same way
    for instance in context:
        instance.data.pop("folderEntity", None)
        instance.data.pop("taskEntity", None)
    plugin = CollectAnatomyInstanceData()
    plugin.fill_missing_folder_entities(context, PROJECT_NAME)
    plugin.fill_missing_task_entities(context, PROJECT_NAME)


def _collected_data(context: pyblish.api.Context) -> dict[str, Any]:
    return {
        "context": {
            key: context.data[key]
            for key in (
                "project_settings",
                "projectEntity",
                "folderEntity",
                "taskEntity",
                "frameStart",
                "fps",
                "hierarchyContext",
            )
        },
        "instances": [
            (
                instance.data.get("folderEntity"),
                instance.data.get("taskEntity"),
            )
            for instance in context
        ],
    }


def test_collectors_use_create_context_cache(server_calls):
    """Collectors do not query the server for data CreateContext has."""
    create_context = _create_create_context()
    server_calls.clear()

    context = _create_publish_context(create_context)
    _collect(context)

    assert server_calls == {}
    assert isinstance(context.data["anatomy"], _FakeAnatomy)
    assert context.data["folderEntity"]["path"] == CONTEXT_FOLDER_PATH
    assert context.data["taskEntity"]["name"] == CONTEXT_TASK_NAME
    folder_paths = [
        (instance.data.get("folderEntity") or {}).get("path")
        for instance in context
    ]
    task_names = [
        (instance.data.get("taskEntity") or {}).get("name")
        for instance in context
    ]
    assert folder_paths == [
        CONTEXT_FOLDER_PATH, "/shots/sh020", "/shots/sh020", None
    ]
    assert task_names == [CONTEXT_TASK_NAME, "anim", None, None]


@pytest.mark.parametrize(
    "folder_path, task_name",
    (
        (MISSING_FOLDER_PATH, CONTEXT_TASK_NAME),
        (CONTEXT_FOLDER_PATH, "missing"),
    ),
)
def test_missing_context_entity_is_not_queried_again(
    server_calls, folder_path, task_name
):
    """Entity missing in CreateContext is not queried from server again."""
    create_context = _create_create_context()
    server_calls.clear()

    context = _create_publish_context(create_context)
    context.data["folderPath"] = folder_path
    context.data["task"] = task_name
    with pytest.raises(PublishError):
        CollectContextEntities().process(context)

    assert server_calls == {}


def test_collected_data_matches_server_data(server_calls):
    """Data from CreateContext cache match data queried from server."""
    cached_context = _create_publish_context(_create_create_context())
    _collect(cached_context)

    server_calls.clear()
    server_context = _create_publish_context(None)
    _collect(server_context)

    # Make sure the fallback really queried the server
    assert server_calls["get_project_settings"] == 1
    assert server_calls["get_project"] == 1
    assert server_calls["get_folders"] > 0
    assert server_calls["get_tasks"] > 0
    assert _collected_data(cached_context) == _collected_data(server_context)


def test_collected_data_does_not_change_create_context(server_calls):
    """Changes of collected data do not affect CreateContext cache."""
    create_context = _create_create_context()
    context = _create_publish_context(create_context)
    _collect(context)

    context.data["project_settings"]["core"]["value"] = 2
    context.data["projectEntity"]["code"] = "changed"
    for instance in context:
        for key in ("folderEntity", "taskEntity"):
            entity = instance.data.get(key)
            if entity:
                entity["attrib"]["fps"] = 1.0

    assert create_context.get_current_project_settings() == PROJECT_SETTINGS
    assert create_context.get_current_project_entity()["code"] == "prj"
    for folder_path, task_names in TASK_NAMES_BY_FOLDER_PATH.items():
        folder_entity = create_context.get_folder_entity(folder_path)
        assert folder_entity["attrib"]["fps"] == 25.0
        for task_name in task_names:
            task_entity = create_context.get_task_entity(
                folder_path, task_name
            )
            assert task_entity["attrib"]["fps"] == 25.0
