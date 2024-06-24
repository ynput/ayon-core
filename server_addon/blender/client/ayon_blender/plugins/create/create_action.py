"""Create an animation asset."""

import bpy

from ayon_blender.api import lib, plugin


class CreateAction(plugin.BlenderCreator):
    """Action output for character rigs."""

    identifier = "io.openpype.creators.blender.action"
    label = "Action"
    product_type = "action"
    icon = "male"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # Run parent create method
        collection = super().create(
            product_name, instance_data, pre_create_data
        )

        # Get instance name
        name = plugin.prepare_scene_name(
            instance_data["folderPath"], product_name
        )

        if pre_create_data.get("use_selection"):
            for obj in lib.get_selection():
                if (obj.animation_data is not None
                        and obj.animation_data.action is not None):

                    empty_obj = bpy.data.objects.new(name=name,
                                                     object_data=None)
                    empty_obj.animation_data_create()
                    empty_obj.animation_data.action = obj.animation_data.action
                    empty_obj.animation_data.action.name = name
                    collection.objects.link(empty_obj)

        return collection
