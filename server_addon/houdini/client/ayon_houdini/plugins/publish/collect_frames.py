# -*- coding: utf-8 -*-
"""Collector plugin for frames data on ROP instances."""
import os
import hou  # noqa
import clique
import pyblish.api
from ayon_houdini.api import lib, plugin


class CollectFrames(plugin.HoudiniInstancePlugin):
    """Collect all frames which would be saved from the ROP nodes"""

    # This specific order value is used so that
    # this plugin runs after CollectRopFrameRange
    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Frames"
    families = ["camera", "vdbcache", "imagesequence", "ass",
                "redshiftproxy", "review", "pointcache", "fbx",
                "model"]

    def process(self, instance):

        # CollectRopFrameRange computes `start_frame` and `end_frame`
        #  depending on the trange value.
        start_frame = instance.data["frameStartHandle"]
        end_frame = instance.data["frameEndHandle"]

        # Evaluate the file name at the first frame.
        ropnode = hou.node(instance.data["instance_node"])
        output_parm = lib.get_output_parameter(ropnode)
        output = output_parm.evalAtFrame(start_frame)
        file_name = os.path.basename(output)

        # todo: `frames` currently conflicts with "explicit frames" for a
        #       for a custom frame list. So this should be refactored.

        instance.data.update({
            "frames": file_name,  # Set frames to the file name by default.
            "stagingDir": os.path.dirname(output)
        })

        # Skip unnecessary logic if start and end frames are equal.
        if start_frame == end_frame:
            return

        # Create collection using frame pattern.
        # e.g. 'pointcacheBgeoCache_AB010.1001.bgeo'
        # will be <Collection "pointcacheBgeoCache_AB010.%d.bgeo [1001]">
        frame_collection, _ = clique.assemble(
            [file_name],
            patterns=[clique.PATTERNS["frames"]],
            minimum_items=1
        )

        # Return as no frame pattern detected.
        if not frame_collection:
            return

        # It's always expected to be one collection.
        frame_collection = frame_collection[0]
        frame_collection.indexes.clear()
        frame_collection.indexes.update(list(range(start_frame, (end_frame + 1))))
        instance.data["frames"] = list(frame_collection)
