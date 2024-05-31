import hou
import pyblish.api
from ayon_houdini.api import plugin


class CollectWorksceneFPS(plugin.HoudiniContextPlugin):
    """Get the FPS of the work scene."""

    label = "Workscene FPS"
    order = pyblish.api.CollectorOrder

    def process(self, context):
        fps = hou.fps()
        self.log.info("Workscene FPS: %s" % fps)
        context.data.update({"fps": fps})
