import os

import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api.lib import render_rop
import hou


class ExtractMantraIFD(publish.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Mantra ifd"
    hosts = ["houdini"]
    families = ["mantraifd"]
    targets = ["local", "remote"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        ropnode = hou.node(instance.data.get("instance_node"))
        output = ropnode.evalParm("soho_diskfile")
        staging_dir, file_name = os.path.split(output)
        instance.data["stagingDir"] = staging_dir
        # render rop
        self.log.debug("Writing IFD '{}' to '{}'".format(file_name, staging_dir))
        render_rop(ropnode)

        files = instance.data["frames"]

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'ifd',
            'ext': 'ifd',
            'files': files,
            "stagingDir": staging_dir,
            "frameStart": instance.data["frameStart"],
            "frameEnd": instance.data["frameEnd"],
        }
        instance.data["representations"].append(representation)
