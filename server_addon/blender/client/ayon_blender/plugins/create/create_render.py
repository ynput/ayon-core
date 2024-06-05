"""Create render."""
import bpy

from ayon_core.lib import version_up
from ayon_blender.api import plugin
from ayon_blender.api.render_lib import prepare_rendering
from ayon_blender.api.workio import save_file


class CreateRenderlayer(plugin.BlenderCreator):
    """Single baked camera."""

    identifier = "io.openpype.creators.blender.render"
    label = "Render"
    product_type = "render"
    icon = "eye"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        try:
            # Run parent create method
            collection = super().create(
                product_name, instance_data, pre_create_data
            )

            prepare_rendering(collection)
        except Exception:
            # Remove the instance if there was an error
            bpy.data.collections.remove(collection)
            raise

        # TODO: this is undesiderable, but it's the only way to be sure that
        # the file is saved before the render starts.
        # Blender, by design, doesn't set the file as dirty if modifications
        # happen by script. So, when creating the instance and setting the
        # render settings, the file is not marked as dirty. This means that
        # there is the risk of sending to deadline a file without the right
        # settings. Even the validator to check that the file is saved will
        # detect the file as saved, even if it isn't. The only solution for
        # now it is to force the file to be saved.
        filepath = version_up(bpy.data.filepath)
        save_file(filepath, copy=False)

        return collection
