# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""
import ayon_api
from ayon_core.pipeline import (
    AutoCreator,
    CreatedInstance,
)


class CreateWorkfile(AutoCreator):
    """Workfile auto-creator."""
    settings_category = "resolve"

    identifier = "io.ayon.creators.resolve.workfile"
    label = "Workfile"
    product_type = "workfile"

    default_variant = "Main"

    def collect_instances(self):

        variant = self.default_variant
        project_name = self.create_context.get_current_project_name()
        folder_path = self.create_context.get_current_folder_path()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path)
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name
        )
        product_name = self.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            self.default_variant,
            host_name,
        )
        data = {
            "folderPath": folder_path,
            "task": task_name,
            "variant": variant,
        }
        data.update(
            self.get_dynamic_data(
                variant,
                task_name,
                folder_entity,
                project_name,
                host_name,
                False,
            )
        )
        self.log.info("Auto-creating workfile instance...")
        current_instance = CreatedInstance(
            self.product_type, product_name, data, self)
        self._add_instance_to_context(current_instance)

    def create(self, options=None):
        # no need to create if it is created
        # in `collect_instances`
        pass

    def update_instances(self, update_list):
        # TODO: Implement
        #   This needs to be implemented to allow persisting any instance
        #   data on resets. We'll need to decide where to store workfile
        #   instance data reliably. Likely metadata on the *current project*?
        pass
