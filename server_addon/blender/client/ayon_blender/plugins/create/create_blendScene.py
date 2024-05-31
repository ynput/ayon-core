"""Create a Blender scene asset."""

import bpy

from ayon_blender.api import plugin, lib


class CreateBlendScene(plugin.BlenderCreator):
    """Generic group of assets."""

    identifier = "io.openpype.creators.blender.blendscene"
    label = "Blender Scene"
    product_type = "blendScene"
    icon = "cubes"

    maintain_selection = False

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):

        instance_node = super().create(product_name,
                                       instance_data,
                                       pre_create_data)

        if pre_create_data.get("use_selection"):
            selection = lib.get_selection(include_collections=True)
            for data in selection:
                if isinstance(data, bpy.types.Collection):
                    instance_node.children.link(data)
                elif isinstance(data, bpy.types.Object):
                    instance_node.objects.link(data)

        return instance_node
