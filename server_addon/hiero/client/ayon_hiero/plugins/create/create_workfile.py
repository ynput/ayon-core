# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""
import ayon_api

from ayon_core.pipeline.create import CreatedInstance, AutoCreator


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
        project_name = self.create_context.get_current_project_name()
        folder_path = self.create_context.get_current_folder_path()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name
        variant = self.default_variant

        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path
        )
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name
        )
        product_name = self.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
        )

        instance_data = {
            "folderPath": folder_path,
            "task": task_name,
            "variant": variant
        }
        instance_data.update(self.get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name
        ))

        instance = CreatedInstance(
            self.family, product_name, instance_data, self
        )
        self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        # for created_inst, _changes in update_list:
        #     instance_node = created_inst.transient_data["node"]
        #     print(instance_node)
        pass