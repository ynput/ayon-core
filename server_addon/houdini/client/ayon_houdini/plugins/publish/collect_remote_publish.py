import hou
import pyblish.api

from ayon_core.pipeline.publish import RepairAction
from ayon_houdini.api import lib, plugin


class CollectRemotePublishSettings(plugin.HoudiniContextPlugin):
    """Collect custom settings of the Remote Publish node."""

    order = pyblish.api.CollectorOrder
    families = ["*"]
    targets = ["deadline"]
    label = "Remote Publish Submission Settings"
    actions = [RepairAction]

    def process(self, context):

        node = hou.node("/out/REMOTE_PUBLISH")
        if not node:
            return

        attributes = lib.read(node)

        # Debug the settings we have collected
        for key, value in sorted(attributes.items()):
            self.log.debug("Collected %s: %s" % (key, value))

        context.data.update(attributes)
