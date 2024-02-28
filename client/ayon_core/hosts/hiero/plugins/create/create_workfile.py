# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""
from ayon_core.pipeline.create import CreatedInstance, AutoCreator
from ayon_core.client import get_asset_by_name


class CreateWorkfile(AutoCreator):
    """Workfile auto-creator."""
    identifier = "io.ayon.creators.hiero.workfile"
    label = "Workfile"
    family = "workfile"
    icon = "fa5.file"

    default_variant = "Main"

    def create(self, options=None):
        pass

    def collect_instances(self):
        instance_data = {}
        project_name = self.create_context.get_current_project_name()
        asset_name = self.create_context.get_current_asset_name()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        print(project_name, asset_name, task_name, host_name)
        asset_doc = get_asset_by_name(project_name, asset_name)
        subset_name = self.get_subset_name(
            self.default_variant, task_name, asset_doc,
            project_name, host_name
        )
        instance_data.update({
            "asset": asset_name,
            "task": task_name,
            "variant": self.default_variant
        })
        instance_data.update(self.get_dynamic_data(
            self.default_variant, task_name, asset_doc,
            project_name, host_name, instance_data
        ))

        instance = CreatedInstance(
            self.family, subset_name, instance_data, self
        )
        self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        # for created_inst, _changes in update_list:
        #     instance_node = created_inst.transient_data["node"]
        #     print(instance_node)
        pass