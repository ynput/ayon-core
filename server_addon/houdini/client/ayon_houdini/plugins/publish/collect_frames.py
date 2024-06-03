# -*- coding: utf-8 -*-
"""Collector plugin for frames data on ROP instances."""
import os
import re

import hou  # noqa
import pyblish.api
from ayon_houdini.api import lib, plugin


class CollectFrames(plugin.HoudiniInstancePlugin):
    """Collect all frames which would be saved from the ROP nodes"""

    # This specific order value is used so that
    # this plugin runs after CollectRopFrameRange
    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Frames"
    families = ["vdbcache", "imagesequence", "ass",
                "mantraifd", "redshiftproxy", "review",
                "pointcache"]

    def process(self, instance):

        ropnode = hou.node(instance.data["instance_node"])

        start_frame = instance.data.get("frameStartHandle", None)
        end_frame = instance.data.get("frameEndHandle", None)

        output_parm = lib.get_output_parameter(ropnode)
        if start_frame is not None:
            # When rendering only a single frame still explicitly
            # get the name for that particular frame instead of current frame
            output = output_parm.evalAtFrame(start_frame)
        else:
            self.log.warning("Using current frame: {}".format(hou.frame()))
            output = output_parm.eval()

        _, ext = lib.splitext(
            output, allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"])
        file_name = os.path.basename(output)
        result = file_name

        # Get the filename pattern match from the output
        # path, so we can compute all frames that would
        # come out from rendering the ROP node if there
        # is a frame pattern in the name
        pattern = r"\w+\.(\d+)" + re.escape(ext)
        match = re.match(pattern, file_name)

        if match and start_frame is not None:

            # Check if frames are bigger than 1 (file collection)
            # override the result
            if end_frame - start_frame > 0:
                result = lib.create_file_list(
                    match, int(start_frame), int(end_frame)
                )

        # todo: `frames` currently conflicts with "explicit frames" for a
        #       for a custom frame list. So this should be refactored.
        instance.data.update({"frames": result})
