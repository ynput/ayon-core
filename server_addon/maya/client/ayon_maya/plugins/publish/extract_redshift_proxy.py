# -*- coding: utf-8 -*-
"""Redshift Proxy extractor."""
import os

from ayon_maya.api.lib import maintained_selection, renderlayer
from ayon_maya.api import plugin
from ayon_maya.api.render_setup_tools import (
    allow_export_from_render_setup_layer,
)
from maya import cmds


class ExtractRedshiftProxy(plugin.MayaExtractorPlugin):
    """Extract the content of the instance to a redshift proxy file."""

    label = "Redshift Proxy (.rs)"
    families = ["redshiftproxy"]

    def process(self, instance):
        """Extractor entry point."""

        # Make sure Redshift is loaded
        cmds.loadPlugin("redshift4maya", quiet=True)

        staging_dir = self.staging_dir(instance)
        file_name = "{}.rs".format(instance.name)
        file_path = os.path.join(staging_dir, file_name)

        anim_on = instance.data["animation"]
        rs_options = "exportConnectivity=0;enableCompression=1;keepUnused=0;"
        repr_files = file_name

        if not anim_on:
            # Remove animation information because it is not required for
            # non-animated products
            keys = ["frameStart",
                    "frameEnd",
                    "handleStart",
                    "handleEnd",
                    "frameStartHandle",
                    "frameEndHandle"]
            for key in keys:
                instance.data.pop(key, None)

        else:
            start_frame = instance.data["frameStartHandle"]
            end_frame = instance.data["frameEndHandle"]
            rs_options = "{}startFrame={};endFrame={};frameStep={};".format(
                rs_options, start_frame,
                end_frame, instance.data["step"]
            )

            root, ext = os.path.splitext(file_path)
            # Padding is taken from number of digits of the end_frame.
            # Not sure where Redshift is taking it.
            repr_files = [
                "{}.{}{}".format(os.path.basename(root), str(frame).rjust(4, "0"), ext)     # noqa: E501
                for frame in range(
                    int(start_frame),
                    int(end_frame) + 1,
                    int(instance.data["step"])
            )]
        # vertex_colors = instance.data.get("vertexColors", False)

        # Write out rs file
        self.log.debug("Writing: '%s'" % file_path)

        # Allow overriding what renderlayer to export from. By default force
        # it to the default render layer. (Note that the renderlayer isn't
        # currently exposed as an attribute to artists)
        layer = instance.data.get("renderLayer", "defaultRenderLayer")

        with maintained_selection():
            with renderlayer(layer):
                with allow_export_from_render_setup_layer():
                    cmds.select(instance.data["setMembers"], noExpand=True)
                    cmds.file(file_path,
                              preserveReferences=False,
                              force=True,
                              type="Redshift Proxy",
                              exportSelected=True,
                              options=rs_options)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        self.log.debug("Files: {}".format(repr_files))

        representation = {
            'name': 'rs',
            'ext': 'rs',
            'files': repr_files,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s"
                       % (instance.name, staging_dir))
