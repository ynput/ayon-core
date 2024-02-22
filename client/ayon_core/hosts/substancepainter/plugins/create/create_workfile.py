# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""

from ayon_core.pipeline import CreatedInstance, AutoCreator
from ayon_core.client import get_asset_by_name

from ayon_core.hosts.substancepainter.api.pipeline import (
    set_instances,
    set_instance,
    get_instances
)

import substance_painter.project


class CreateWorkfile(AutoCreator):
    """Workfile auto-creator."""
    identifier = "io.openpype.creators.substancepainter.workfile"
    label = "Workfile"
    product_type = "workfile"
    icon = "document"

    default_variant = "Main"

    def create(self):

        if not substance_painter.project.is_open():
            return

        variant = self.default_variant
        project_name = self.project_name
        asset_name = self.create_context.get_current_asset_name()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        # Workfile instance should always exist and must only exist once.
        # As such we'll first check if it already exists and is collected.
        current_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ), None)

        if current_instance is None:
            current_instance_asset = None
        else:
            current_instance_asset = current_instance["folderPath"]

        if current_instance is None:
            self.log.info("Auto-creating workfile instance...")
            asset_doc = get_asset_by_name(project_name, asset_name)
            product_name = self.get_product_name(
                variant, task_name, asset_doc, project_name, host_name
            )
            data = {
                "folderPath": asset_name,
                "task": task_name,
                "variant": variant
            }
            current_instance = self.create_instance_in_context(product_name,
                                                               data)
        elif (
            current_instance_asset != asset_name
            or current_instance["task"] != task_name
        ):
            # Update instance context if is not the same
            asset_doc = get_asset_by_name(project_name, asset_name)
            product_name = self.get_product_name(
                variant, task_name, asset_doc, project_name, host_name
            )
            current_instance["folderPath"] = asset_name
            current_instance["task"] = task_name
            current_instance["productName"] = product_name

        set_instance(
            instance_id=current_instance.get("instance_id"),
            instance_data=current_instance.data_to_store()
        )

    def collect_instances(self):
        for instance in get_instances():
            if (instance.get("creator_identifier") == self.identifier or
                    instance.get("productType") == self.product_type):
                self.create_instance_in_context_from_existing(instance)

    def update_instances(self, update_list):
        instance_data_by_id = {}
        for instance, _changes in update_list:
            # Persist the data
            instance_id = instance.get("instance_id")
            instance_data = instance.data_to_store()
            instance_data_by_id[instance_id] = instance_data
        set_instances(instance_data_by_id, update=True)

    # Helper methods (this might get moved into Creator class)
    def create_instance_in_context(self, product_name, data):
        instance = CreatedInstance(
            self.product_type, product_name, data, self
        )
        self.create_context.creator_adds_instance(instance)
        return instance

    def create_instance_in_context_from_existing(self, data):
        instance = CreatedInstance.from_existing(data, self)
        self.create_context.creator_adds_instance(instance)
        return instance
