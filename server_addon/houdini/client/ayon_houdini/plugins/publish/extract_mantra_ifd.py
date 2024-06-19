import os
import hou

import pyblish.api

from ayon_houdini.api import plugin


class ExtractMantraIFD(plugin.HoudiniExtractorPlugin):

    order = pyblish.api.ExtractorOrder
    label = "Extract Mantra ifd"
    families = ["mantraifd"]
    targets = ["local", "remote"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        ropnode = hou.node(instance.data.get("instance_node"))
        output = ropnode.evalParm("soho_diskfile")
        staging_dir = os.path.dirname(output)
        instance.data["stagingDir"] = staging_dir

        self.validate_expected_frames(instance, staging_dir)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'ifd',
            'ext': 'ifd',
            'files': instance.data["frames"],
            "stagingDir": staging_dir,
            "frameStart": instance.data["frameStart"],
            "frameEnd": instance.data["frameEnd"],
        }
        instance.data["representations"].append(representation)
