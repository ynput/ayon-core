"""Create a rig asset."""

import bpy

from ayon_core.lib import NumberDef
from ayon_blender.api import plugin, lib


class CreateRig(plugin.BlenderCreator):
    """Artist-friendly rig with controls to direct motion."""

    identifier = "io.openpype.creators.blender.rig"
    label = "Rig"
    product_type = "rig"
    icon = "wheelchair"

    create_as_asset_group = True

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        asset_group = super().create(product_name,
                                     instance_data,
                                     pre_create_data)

        # Add selected objects to instance
        if pre_create_data.get("use_selection"):
            bpy.context.view_layer.objects.active = asset_group
            for obj in lib.get_selection():
                obj.parent = asset_group

        return asset_group

    def get_instance_attr_defs(self):
        return [
            NumberDef("unitScale",
                      label="Unit Scale (FBX)",
                      default=1.0,
                      tooltip="Scale of the model, valid only for FBX export.")
        ]
