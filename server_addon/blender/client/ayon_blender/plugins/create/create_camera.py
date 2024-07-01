"""Create a camera asset."""

import bpy

from ayon_core.lib import NumberDef
from ayon_blender.api import plugin, lib
from ayon_blender.api.pipeline import AVALON_INSTANCES


class CreateCamera(plugin.BlenderCreator):
    """Polygonal static geometry."""

    identifier = "io.openpype.creators.blender.camera"
    label = "Camera"
    product_type = "camera"
    icon = "video-camera"

    create_as_asset_group = True

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):

        asset_group = super().create(product_name,
                                     instance_data,
                                     pre_create_data)

        bpy.context.view_layer.objects.active = asset_group
        if pre_create_data.get("use_selection"):
            for obj in lib.get_selection():
                obj.parent = asset_group
        else:
            plugin.deselect_all()
            camera = bpy.data.cameras.new(product_name)
            camera_obj = bpy.data.objects.new(product_name, camera)

            instances = bpy.data.collections.get(AVALON_INSTANCES)
            instances.objects.link(camera_obj)

            bpy.context.view_layer.objects.active = asset_group
            camera_obj.parent = asset_group

        return asset_group

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs()

        defs.append(
            NumberDef("unitScale",
                      label="Unit Scale (FBX)",
                      default=1.0,
                      tooltip="Scale of the model, valid only for FBX export.")
        )

        return defs
