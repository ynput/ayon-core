import pyblish.api
from ayon_maya.api.plugin import MayaContextPlugin
from maya import mel


class CollectWorksceneFPS(MayaContextPlugin):
    """Get the FPS of the work scene"""

    label = "Workscene FPS"
    order = pyblish.api.CollectorOrder

    def process(self, context):
        fps = mel.eval('currentTimeUnitToFPS()')
        self.log.info("Workscene FPS: %s" % fps)
        context.data.update({"fps": fps})
