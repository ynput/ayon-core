import ayon_api

from ayon_core.pipeline import (
    AutoCreator,
    CreatedInstance
)
from ayon_aftereffects import api
from ayon_aftereffects.api.pipeline import cache_and_get_instances


class AEWorkfileCreator(AutoCreator):
    identifier = "workfile"
    product_type = "workfile"

    default_variant = "Main"

    def get_instance_attr_defs(self):
        return []

    def collect_instances(self):
        for instance_data in cache_and_get_instances(self):
            creator_id = instance_data.get("creator_identifier")
            if creator_id == self.identifier:
                product_name = instance_data["productName"]
                instance = CreatedInstance(
                    self.product_type, product_name, instance_data, self
                )
                self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        # nothing to change on workfiles
        pass

    def create(self, options=None):
        existing_instance = None
        for instance in self.create_context.instances:
            if instance.product_type == self.product_type:
                existing_instance = instance
                break

        context = self.create_context
        project_name = context.get_current_project_name()
        folder_path = context.get_current_folder_path()
        task_name = context.get_current_task_name()
        host_name = context.host_name

        existing_folder_path = None
        if existing_instance is not None:
            existing_folder_path = existing_instance.get("folderPath")

        if existing_instance is None:
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
                self.default_variant,
                host_name,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "variant": self.default_variant,
            }
            data.update(self.get_dynamic_data(
                project_name,
                folder_entity,
                task_entity,
                self.default_variant,
                host_name,
                None,
            ))

            new_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            self._add_instance_to_context(new_instance)

            api.get_stub().imprint(new_instance.get("instance_id"),
                                   new_instance.data_to_store())

        elif (
            existing_folder_path != folder_path
            or existing_instance["task"] != task_name
        ):
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
                self.default_variant,
                host_name,
            )
            existing_instance["folderPath"] = folder_path
            existing_instance["task"] = task_name
            existing_instance["productName"] = product_name
