import os
import json

import clique
import pyblish.api

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import capture, plugin
from ayon_blender.api.lib import maintained_time


class ExtractPlayblast(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """
    Extract viewport playblast.

    Takes review camera and creates review Quicktime video based on viewport
    capture.
    """

    label = "Extract Playblast"
    hosts = ["blender"]
    families = ["review"]
    optional = True
    order = pyblish.api.ExtractorOrder + 0.01

    presets = "{}"

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # get scene fps
        fps = instance.data.get("fps")
        if fps is None:
            fps = bpy.context.scene.render.fps
            instance.data["fps"] = fps

        self.log.debug(f"fps: {fps}")

        # If start and end frames cannot be determined,
        # get them from Blender timeline.
        start = instance.data.get("frameStart", bpy.context.scene.frame_start)
        end = instance.data.get("frameEnd", bpy.context.scene.frame_end)

        self.log.debug(f"start: {start}, end: {end}")
        assert end > start, "Invalid time range !"

        # get cameras
        camera = instance.data("review_camera", None)

        # get isolate objects list
        isolate = instance.data("isolate", None)

        # get output path
        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        filename = f"{folder_name}_{product_name}"

        path = os.path.join(stagingdir, filename)

        self.log.debug(f"Outputting images to {path}")

        presets = json.loads(self.presets)
        preset = presets.get("default")
        preset.update({
            "camera": camera,
            "start_frame": start,
            "end_frame": end,
            "filename": path,
            "overwrite": True,
            "isolate": isolate,
        })
        preset.setdefault(
            "image_settings",
            {
                "file_format": "PNG",
                "color_mode": "RGB",
                "color_depth": "8",
                "compression": 15,
            },
        )

        with maintained_time():
            path = capture(**preset)

        self.log.debug(f"playblast path {path}")

        collected_files = os.listdir(stagingdir)
        collections, remainder = clique.assemble(
            collected_files,
            patterns=[f"{filename}\\.{clique.DIGITS_PATTERN}\\.png$"],
        )

        if len(collections) > 1:
            raise RuntimeError(
                f"More than one collection found in stagingdir: {stagingdir}"
            )
        elif len(collections) == 0:
            raise RuntimeError(
                f"No collection found in stagingdir: {stagingdir}"
            )

        frame_collection = collections[0]

        self.log.debug(f"Found collection of interest {frame_collection}")

        instance.data.setdefault("representations", [])

        tags = ["review"]
        if not instance.data.get("keepImages"):
            tags.append("delete")

        representation = {
            "name": "png",
            "ext": "png",
            "files": list(frame_collection),
            "stagingDir": stagingdir,
            "frameStart": start,
            "frameEnd": end,
            "fps": fps,
            "tags": tags,
            "camera_name": camera
        }
        instance.data["representations"].append(representation)
