import os

import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api.lib import render_rop

import hou


class ExtractAlembic(publish.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Alembic"
    hosts = ["houdini"]
    families = ["abc", "camera"]
    targets = ["local", "remote"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        ropnode = hou.node(instance.data["instance_node"])

        # Get the filename from the filename parameter
        output = ropnode.evalParm("filename")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir

        if instance.data.get("frames"):
            # list of files
            files = instance.data["frames"]
        else:
            # single file
            files = os.path.basename(output)

        # We run the render
        self.log.info("Writing alembic '%s' to '%s'" % (files,
                                                        staging_dir))

        render_rop(ropnode)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'abc',
            'ext': 'abc',
            'files': files,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)
