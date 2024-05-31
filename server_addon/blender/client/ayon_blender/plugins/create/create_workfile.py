import bpy
import ayon_api

from ayon_core.pipeline import CreatedInstance, AutoCreator
from ayon_blender.api.plugin import BlenderCreator
from ayon_blender.api.pipeline import (
    AVALON_PROPERTY,
    AVALON_CONTAINERS
)


class CreateWorkfile(BlenderCreator, AutoCreator):
    """Workfile auto-creator.

    The workfile instance stores its data on the `AVALON_CONTAINERS` collection
    as custom attributes, because unlike other instances it doesn't have an
    instance node of its own.

    """
    identifier = "io.openpype.creators.blender.workfile"
    label = "Workfile"
    product_type = "workfile"
    icon = "fa5.file"

    def create(self):
        """Create workfile instances."""
        workfile_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ),
            None,
        )

        project_name = self.project_name
        folder_path = self.create_context.get_current_folder_path()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        existing_folder_path = None
        if workfile_instance is not None:
            existing_folder_path = workfile_instance.get("folderPath")

        if not workfile_instance:
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
                task_name,
                host_name,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "variant": task_name,
            }
            data.update(
                self.get_dynamic_data(
                    project_name,
                    folder_entity,
                    task_entity,
                    task_name,
                    host_name,
                    workfile_instance,
                )
            )
            self.log.info("Auto-creating workfile instance...")
            workfile_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            self._add_instance_to_context(workfile_instance)

        elif (
            existing_folder_path != folder_path
            or workfile_instance["task"] != task_name
        ):
            # Update instance context if it's different
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

            workfile_instance["folderPath"] = folder_path
            workfile_instance["task"] = task_name
            workfile_instance["productName"] = product_name

        instance_node = bpy.data.collections.get(AVALON_CONTAINERS)
        if not instance_node:
            instance_node = bpy.data.collections.new(name=AVALON_CONTAINERS)
        workfile_instance.transient_data["instance_node"] = instance_node

    def collect_instances(self):

        instance_node = bpy.data.collections.get(AVALON_CONTAINERS)
        if not instance_node:
            return

        property = instance_node.get(AVALON_PROPERTY)
        if not property:
            return

        # Create instance object from existing data
        instance = CreatedInstance.from_existing(
            instance_data=property.to_dict(),
            creator=self
        )
        instance.transient_data["instance_node"] = instance_node

        # Add instance to create context
        self._add_instance_to_context(instance)

    def remove_instances(self, instances):
        for instance in instances:
            node = instance.transient_data["instance_node"]
            del node[AVALON_PROPERTY]

            self._remove_instance_from_context(instance)
