import os
import hou

import pyblish.api

from ayon_houdini.api import plugin
from ayon_houdini.api.lib import render_rop


class ExtractRender(plugin.HoudiniExtractorPlugin):

    order = pyblish.api.ExtractorOrder
    label = "Extract Render"
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    def process(self, instance):
        creator_attribute = instance.data["creator_attributes"]
        product_type = instance.data["productType"]
        rop_node = hou.node(instance.data.get("instance_node"))

        # Align split parameter value on rop node to the render target.
        if instance.data["splitRender"]:
            if product_type == "arnold_rop":
                rop_node.setParms({"ar_ass_export_enable": 1})
            elif product_type == "mantra_rop":
                rop_node.setParms({"soho_outputmode": 1})
            elif product_type == "redshift_rop":
                rop_node.setParms({"RS_archive_enable": 1})
            elif product_type == "vray_rop":
                rop_node.setParms({"render_export_mode": "2"})
        else:
            if product_type == "arnold_rop":
                rop_node.setParms({"ar_ass_export_enable": 0})
            elif product_type == "mantra_rop":
                rop_node.setParms({"soho_outputmode": 0})
            elif product_type == "redshift_rop":
                rop_node.setParms({"RS_archive_enable": 0})
            elif product_type == "vray_rop":
                rop_node.setParms({"render_export_mode": "1"})

        if instance.data.get("farm"):
            self.log.debug("Render should be processed on farm, skipping local render.")
            return

        if creator_attribute.get("render_target") == "local":
            ropnode = hou.node(instance.data.get("instance_node"))
            render_rop(ropnode)

        # `ExpectedFiles` is a list that includes one dict.
        expected_files = instance.data["expectedFiles"][0]
        # Each key in that dict is a list of files.
        # Combine lists of files into one big list.
        all_frames = []
        for value in  expected_files.values():
            if isinstance(value, str):
                all_frames.append(value)
            elif isinstance(value, list):
                all_frames.extend(value)
        # Check missing frames.
        # Frames won't exist if user cancels the render.
        missing_frames = [
            frame
            for frame in all_frames
            if not os.path.exists(frame)
        ]
        if missing_frames:
            # TODO: Use user friendly error reporting.
            raise RuntimeError("Failed to complete render extraction. "
                               "Missing output files: {}".format(
                                   missing_frames))
