import os
import hou

import pyblish.api

from ayon_houdini.api import lib, plugin


class ExtractBGEO(plugin.HoudiniExtractorPlugin):

    order = pyblish.api.ExtractorOrder
    label = "Extract BGEO"
    families = ["bgeo"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return
        ropnode = hou.node(instance.data["instance_node"])

        # Get the filename from the filename parameter
        output = ropnode.evalParm("sopoutput")
        staging_dir, file_name = os.path.split(output)
        instance.data["stagingDir"] = staging_dir

        # We run the render
        self.log.info("Writing bgeo files '{}' to '{}'.".format(
            file_name, staging_dir))

        # write files
        lib.render_rop(ropnode)

        output = instance.data["frames"]

        _, ext = lib.splitext(
            output[0], allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"])

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            "name": "bgeo",
            "ext": ext.lstrip("."),
            "files": output,
            "stagingDir": staging_dir,
            "frameStart": instance.data["frameStartHandle"],
            "frameEnd": instance.data["frameEndHandle"]
        }
        instance.data["representations"].append(representation)
