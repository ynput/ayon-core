import pyblish.api
from ayon_maya.api import plugin
from maya import cmds


class CollectModelData(plugin.MayaInstancePlugin):
    """Collect model data

    Ensures always only a single frame is extracted (current frame).

    Todo:
        Validate if is this plugin still useful.

    Note:
        This is a workaround so that the `model` product type can use the
        same pointcache extractor implementation as animation and pointcaches.
        This always enforces the "current" frame to be published.

    """

    order = pyblish.api.CollectorOrder + 0.2
    label = 'Collect Model Data'
    families = ["model"]

    def process(self, instance):
        # Extract only current frame (override)
        frame = cmds.currentTime(query=True)
        instance.data["frameStart"] = frame
        instance.data["frameEnd"] = frame
