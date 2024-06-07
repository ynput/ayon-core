import os

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin


class ExtractBlendAnimation(
    plugin.BlenderExtractor,
    publish.OptionalPyblishPluginMixin,
):
    """Extract a blend file."""

    label = "Extract Blend"
    hosts = ["blender"]
    families = ["animation"]
    optional = True

    # From settings
    compress = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Define extract output file path

        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        instance_name = f"{folder_name}_{product_name}"
        filename = f"{instance_name}.blend"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        data_blocks = set()

        for obj in instance:
            if isinstance(obj, bpy.types.Object) and obj.type == 'EMPTY':
                child = obj.children[0]
                if child and child.type == 'ARMATURE':
                    if child.animation_data and child.animation_data.action:
                        if not obj.animation_data:
                            obj.animation_data_create()
                        obj.animation_data.action = child.animation_data.action
                        obj.animation_data_clear()
                        data_blocks.add(child.animation_data.action)
                        data_blocks.add(obj)

        bpy.data.libraries.write(filepath, data_blocks, compress=self.compress)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'blend',
            'ext': 'blend',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)
