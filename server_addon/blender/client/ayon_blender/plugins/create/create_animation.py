"""Create an animation asset."""

from ayon_core.lib import NumberDef
from ayon_blender.api import plugin, lib


class CreateAnimation(plugin.BlenderCreator):
    """Animation output for character rigs."""

    identifier = "io.openpype.creators.blender.animation"
    label = "Animation"
    product_type = "animation"
    icon = "male"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # Run parent create method
        collection = super().create(
            product_name, instance_data, pre_create_data
        )

        if pre_create_data.get("use_selection"):
            selected = lib.get_selection()
            for obj in selected:
                collection.objects.link(obj)
        elif pre_create_data.get("asset_group"):
            # Use for Load Blend automated creation of animation instances
            # upon loading rig files
            obj = pre_create_data.get("asset_group")
            collection.objects.link(obj)

        return collection

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs()

        defs.append(
            NumberDef("unitScale",
                      label="Unit Scale (FBX)",
                      default=1.0,
                      tooltip="Scale of the model, valid only for FBX export.")
        )

        return defs
