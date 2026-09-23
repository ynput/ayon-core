"""Tests for CreateContext reset performance related behavior."""
from unittest.mock import patch

import pyblish.api
import pytest

from ayon_core.lib import BoolDef
from ayon_core.pipeline.create import (
    CreateContext,
    Creator,
    CreatedInstance,
    register_creator_plugin,
    deregister_creator_plugin,
)
from ayon_core.pipeline.plugin_discover import DiscoverResult
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_core.tools.publisher.models.create import CreatorItem

FOLDER_PATHS = [f"/shots/sh{idx:03}" for idx in range(10)]
# Only folders with even index have a task
FOLDERS_WITH_TASK = set(FOLDER_PATHS[::2])


class _Host:
    name = "test"

    def get_current_context(self):
        return {
            "project_name": "project",
            "folder_path": FOLDER_PATHS[0],
            "task_name": "comp",
        }

    def get_context_data(self):
        return {}

    def update_context_data(self, data, changes):
        pass

    def get_context_title(self):
        return "Test"


class _TestCreator(Creator):
    identifier = "test.creator"
    label = "Test"
    product_base_type = "model"
    product_type = "model"

    pre_create_attr_defs_calls = 0

    def collect_instances(self):
        for idx, folder_path in enumerate(FOLDER_PATHS):
            instance = CreatedInstance.from_existing(
                {
                    "folderPath": folder_path,
                    "task": "comp",
                    "variant": f"v{idx}",
                    "productName": f"model{idx}",
                    "productType": "model",
                    "creator_identifier": self.identifier,
                },
                self,
            )
            self._add_instance_to_context(instance)

    def get_pre_create_attr_defs(self):
        _TestCreator.pre_create_attr_defs_calls += 1
        return [BoolDef("test")]

    def create(self, *args, **kwargs):
        pass

    def update_instances(self, *args, **kwargs):
        pass

    def remove_instances(self, *args, **kwargs):
        pass


class _CollectTaskEntity(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    families = ["model"]
    optional = True

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        # Plugin asks for entities per instance
        create_context.get_task_entity(instance["folderPath"], "comp")
        return super().get_attr_defs_for_instance(create_context, instance)


@pytest.fixture
def server_calls():
    calls = {"folders": 0, "tasks": 0}

    def get_folders(project_name, folder_paths=None, **kwargs):
        calls["folders"] += 1
        for folder_path in folder_paths or []:
            yield {
                "id": folder_path,
                "path": folder_path,
                "name": folder_path.rsplit("/", 1)[-1],
            }

    def get_tasks(project_name, folder_ids=None, **kwargs):
        calls["tasks"] += 1
        for folder_id in folder_ids:
            if folder_id in FOLDERS_WITH_TASK:
                yield {
                    "id": f"{folder_id}/comp",
                    "name": "comp",
                    "folderId": folder_id,
                    "taskType": "Compositing",
                }

    def discover():
        result = DiscoverResult(pyblish.api.Plugin)
        result.plugins = [_CollectTaskEntity]
        return result

    context_module = "ayon_core.pipeline.create.context"
    register_creator_plugin(_TestCreator)
    try:
        with (
            patch(f"{context_module}.ayon_api.get_folders", get_folders),
            patch(f"{context_module}.ayon_api.get_tasks", get_tasks),
            patch(
                f"{context_module}.get_project_settings",
                lambda project_name: {},
            ),
            patch(
                "ayon_core.pipeline.publish.publish_plugins_discover",
                discover,
            ),
        ):
            yield calls
    finally:
        deregister_creator_plugin(_TestCreator)


def test_reset_fetches_entities_in_bulk(server_calls):
    """Entities are fetched once for all instances during reset."""
    create_context = CreateContext(_Host())

    assert len(create_context.instances_by_id) == len(FOLDER_PATHS)
    assert server_calls == {"folders": 1, "tasks": 1}
    for instance in create_context.instances:
        assert "_CollectTaskEntity" in instance.publish_attributes

    # Folders without tasks are cached too
    for folder_path in FOLDER_PATHS:
        create_context.get_task_entity(folder_path, "comp")
    create_context.get_instances_context_info()
    assert server_calls == {"folders": 1, "tasks": 1}


def test_missing_task_is_invalid(server_calls):
    """Task which does not exist on folder is not valid."""
    create_context = CreateContext(_Host(), reset=False)
    create_context.reset_current_context()
    create_context.reset_plugins()
    create_context.reset_context_data()
    # Collect instances without validation of 'bulk_add_instances'
    #   so context info is validated with empty cache
    create_context.reset_instances()

    info_by_id = create_context.get_instances_context_info()
    for instance in create_context.instances:
        context_info = info_by_id[instance.id]
        assert context_info.folder_is_valid
        expected = instance["folderPath"] in FOLDERS_WITH_TASK
        assert context_info.task_is_valid is expected
