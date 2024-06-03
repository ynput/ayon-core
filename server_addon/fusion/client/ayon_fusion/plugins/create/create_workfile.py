import ayon_api

from ayon_fusion.api import (
    get_current_comp
)
from ayon_core.pipeline import (
    AutoCreator,
    CreatedInstance,
)


class FusionWorkfileCreator(AutoCreator):
    identifier = "workfile"
    product_type = "workfile"
    label = "Workfile"
    icon = "fa5.file"

    default_variant = "Main"

    create_allow_context_change = False

    data_key = "openpype_workfile"

    def collect_instances(self):

        comp = get_current_comp()
        data = comp.GetData(self.data_key)
        if not data:
            return

        product_name = data.get("productName")
        if product_name is None:
            product_name = data["subset"]
        instance = CreatedInstance(
            product_type=self.product_type,
            product_name=product_name,
            data=data,
            creator=self
        )
        instance.transient_data["comp"] = comp

        self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        for created_inst, _changes in update_list:
            comp = created_inst.transient_data["comp"]
            if not hasattr(comp, "SetData"):
                # Comp is not alive anymore, likely closed by the user
                self.log.error("Workfile comp not found for existing instance."
                               " Comp might have been closed in the meantime.")
                continue

            # Imprint data into the comp
            data = created_inst.data_to_store()
            comp.SetData(self.data_key, data)

    def create(self, options=None):
        comp = get_current_comp()
        if not comp:
            self.log.error("Unable to find current comp")
            return

        existing_instance = None
        for instance in self.create_context.instances:
            if instance.product_type == self.product_type:
                existing_instance = instance
                break

        project_name = self.create_context.get_current_project_name()
        folder_path = self.create_context.get_current_folder_path()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        existing_folder_path = None
        if existing_instance is not None:
            existing_folder_path = existing_instance["folderPath"]

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
                None

            ))

            new_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            new_instance.transient_data["comp"] = comp
            self._add_instance_to_context(new_instance)

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
