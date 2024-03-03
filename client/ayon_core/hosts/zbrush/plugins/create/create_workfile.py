# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""
from ayon_core.pipeline import CreatedInstance
from ayon_core.client import get_asset_by_name, get_asset_name_identifier
from ayon_core.hosts.zbrush.api import plugin

class CreateWorkfile(plugin.ZbrushAutoCreator):
    """Workfile auto-creator."""
    identifier = "io.ayon.creators.zbrush.workfile"
    label = "Workfile"
    product_type = "workfile"
    icon = "fa5.file"

    default_variant = "Main"

    def create(self):
        variant = self.default_variant
        current_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ), None)
        project_name = self.project_name
        asset_name = self.create_context.get_current_asset_name()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        if current_instance is None:
            current_instance_asset = None
        else:
            current_instance_asset = current_instance["folderPath"]

        if current_instance is None:
            asset_doc = get_asset_by_name(project_name, asset_name)
            subset_name = self.get_product_name(
                project_name,
                asset_doc,
                task_name,
                variant,
                host_name
            )
            data = {
                "task": task_name,
                "variant": variant,
                "folderPath": asset_name
            }

            new_instance = CreatedInstance(
                self.product_type, subset_name, data, self
            )
            instances_data = self.host.list_instances()
            instances_data.append(new_instance.data_to_store())
            self.host.write_instances(instances_data)
            self._add_instance_to_context(new_instance)

        elif (
            current_instance_asset != asset_name
            or current_instance["task"] != task_name
        ):
            # Update instance context if is not the same
            asset_doc = get_asset_by_name(project_name, asset_name)
            subset_name = self.get_subset_name(
                variant, task_name, asset_doc, project_name, host_name
            )
            asset_name = get_asset_name_identifier(asset_doc)

            current_instance["folderPath"] = asset_name
            current_instance["task"] = task_name
            current_instance["subset"] = subset_name
