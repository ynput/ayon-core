from ayon_core.hosts.fusion.api import (
    get_current_comp
)
from ayon_core.client import get_asset_by_name
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
        asset_name = self.create_context.get_current_asset_name()
        task_name = self.create_context.get_current_task_name()
        host_name = self.create_context.host_name

        if existing_instance is None:
            existing_instance_asset = None
        else:
            existing_instance_asset = existing_instance["folderPath"]

        if existing_instance is None:
            asset_doc = get_asset_by_name(project_name, asset_name)
            product_name = self.get_product_name(
                project_name,
                asset_doc,
                task_name,
                self.default_variant,
                host_name,
            )
            data = {
                "folderPath": asset_name,
                "task": task_name,
                "variant": self.default_variant,
            }
            data.update(self.get_dynamic_data(
                self.default_variant, task_name, asset_doc,
                project_name, host_name, None
            ))

            new_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            new_instance.transient_data["comp"] = comp
            self._add_instance_to_context(new_instance)

        elif (
            existing_instance_asset != asset_name
            or existing_instance["task"] != task_name
        ):
            asset_doc = get_asset_by_name(project_name, asset_name)
            product_name = self.get_product_name(
                project_name,
                asset_doc,
                task_name,
                self.default_variant,
                host_name,
            )
            existing_instance["folderPath"] = asset_name
            existing_instance["task"] = task_name
            existing_instance["productName"] = product_name
