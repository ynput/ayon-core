import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api.lib import render_rop
import hou
import os


class ExtractLocalRender(publish.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Local Render"
    hosts = ["houdini"]
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        creator_attribute = instance.data["creator_attributes"]

        if creator_attribute.get("render_target") == "local_no_render":
            self.log.debug("Skip render is enabled, skipping rendering.")
            return

        # Make sure split parameter is turned off.
        # Otherwise, render nodes will generate intermediate
        #  render files instead of render.
        product_type = instance.data["productType"]
        rop_node = hou.node(instance.data.get("instance_node"))

        if product_type == "arnold_rop":
            rop_node.setParms({"ar_ass_export_enable": 0})
        elif product_type == "mantra_rop":
            rop_node.setParms({"soho_outputmode": 0})
        elif product_type == "redshift_rop":
            rop_node.setParms({"RS_archive_enable": 0})
        elif product_type == "vray_rop":
            rop_node.setParms({"render_export_mode": "1"})

        ropnode = hou.node(instance.data.get("instance_node"))
        render_rop(ropnode)

        # Check missing frames.
        # Frames won't exist if user cancels the render.
        expected_files = next(iter(instance.data["expectedFiles"]), {})
        # TODO: enhance the readability.
        expected_files = sum(expected_files.values(), [])
        missing_frames = [
            frame
            for frame in expected_files
            if not os.path.exists(frame)
        ]
        if missing_frames:
            # TODO: Use user friendly error reporting.
            raise RuntimeError("Failed to complete render extraction. "
                               "Missing output files: {}".format(
                                   missing_frames))
