import os
import glob
import json

import pyblish.api
from ayon_blender.api import capture, plugin
from ayon_blender.api.lib import maintained_time

import bpy


class ExtractThumbnail(plugin.BlenderExtractor):
    """Extract viewport thumbnail.

    Takes review camera and creates a thumbnail based on viewport
    capture.

    """

    label = "Extract Thumbnail"
    hosts = ["blender"]
    families = ["review"]
    order = pyblish.api.ExtractorOrder + 0.01
    presets = "{}"

    def process(self, instance):
        self.log.debug("Extracting capture..")

        if instance.data.get("thumbnailSource"):
            self.log.debug("Thumbnail source found, skipping...")
            return

        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        filename = f"{folder_name}_{product_name}"

        path = os.path.join(stagingdir, filename)

        self.log.debug(f"Outputting images to {path}")

        camera = instance.data.get("review_camera", "AUTO")
        start = instance.data.get("frameStart", bpy.context.scene.frame_start)
        product_type = instance.data["productType"]
        isolate = instance.data("isolate", None)

        presets = json.loads(self.presets)
        preset = presets.get(product_type, {})

        preset.update({
            "camera": camera,
            "start_frame": start,
            "end_frame": start,
            "filename": path,
            "overwrite": True,
            "isolate": isolate,
        })
        preset.setdefault(
            "image_settings",
            {
                "file_format": "JPEG",
                "color_mode": "RGB",
                "quality": 100,
            },
        )

        with maintained_time():
            path = capture(**preset)

        thumbnail = os.path.basename(self._fix_output_path(path))

        self.log.debug(f"thumbnail: {thumbnail}")

        instance.data.setdefault("representations", [])

        representation = {
            "name": "thumbnail",
            "ext": "jpg",
            "files": thumbnail,
            "stagingDir": stagingdir,
            "thumbnail": True
        }
        instance.data["representations"].append(representation)

    def _fix_output_path(self, filepath):
        """"Workaround to return correct filepath.

        To workaround this we just glob.glob() for any file extensions and
        assume the latest modified file is the correct file and return it.

        """
        # Catch cancelled playblast
        if filepath is None:
            self.log.warning(
                "Playblast did not result in output path. "
                "Playblast is probably interrupted."
            )
            return None

        if not os.path.exists(filepath):
            files = glob.glob(f"{filepath}.*.jpg")

            if not files:
                raise RuntimeError(f"Couldn't find playblast from: {filepath}")
            filepath = max(files, key=os.path.getmtime)

        return filepath
