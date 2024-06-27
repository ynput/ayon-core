import os
import hou
import pyblish.api
from ayon_houdini.api import (
    lib,
    plugin
)


class CollectDataforCache(plugin.HoudiniInstancePlugin):
    """Collect data for caching to Deadline."""

    # Run after Collect Frames
    order = pyblish.api.CollectorOrder + 0.11
    families = ["ass", "pointcache", "redshiftproxy", "vdbcache", "model"]
    targets = ["local", "remote"]
    label = "Collect Data for Cache"

    def process(self, instance):
        creator_attribute = instance.data["creator_attributes"]
        farm_enabled = creator_attribute["farm"]
        instance.data["farm"] = farm_enabled
        if not farm_enabled:
            self.log.debug("Caching on farm is disabled. "
                           "Skipping farm collecting.")
            return
        # Why do we need this particular collector to collect the expected
        # output files from a ROP node. Don't we have a dedicated collector
        # for that yet?
        # Answer: No, we don't have a generic expected file collector.
        #         Because different product types needs different logic.
        #         e.g. check CollectMantraROPRenderProducts
        #               and CollectKarmaROPRenderProducts
        # Collect expected files
        ropnode = hou.node(instance.data["instance_node"])
        output_parm = lib.get_output_parameter(ropnode)
        expected_filepath = output_parm.eval()
        instance.data.setdefault("files", list())
        instance.data.setdefault("expectedFiles", list())

        frames = instance.data.get("frames", "")
        if isinstance(frames, str):
            # single file
            instance.data["files"].append(expected_filepath)
        else:
            # list of files
            staging_dir, _ = os.path.split(expected_filepath)
            instance.data["files"].extend(
                ["{}/{}".format(staging_dir, f) for f in frames]
            )

        cache_files = {"cache": instance.data["files"]}

        instance.data.update({
            "plugin": "Houdini",
            "publish": True
        })
        instance.data["families"].append("publish.hou")
        instance.data["expectedFiles"].append(cache_files)

        self.log.debug("Caching on farm expected files: {}".format(instance.data["expectedFiles"]))
