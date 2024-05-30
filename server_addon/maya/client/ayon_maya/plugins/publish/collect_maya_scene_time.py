import pyblish.api
from ayon_maya.api import plugin
from maya import cmds


class CollectMayaSceneTime(plugin.MayaInstancePlugin):
    """Collect Maya Scene playback range

    This allows to reproduce the playback range for the content to be loaded.
    It does *not* limit the extracted data to only data inside that time range.

    """

    order = pyblish.api.CollectorOrder + 0.2
    label = 'Collect Maya Scene Time'
    families = ["mayaScene"]

    def process(self, instance):
        instance.data.update({
            "frameStart": int(
                cmds.playbackOptions(query=True, minTime=True)),
            "frameEnd": int(
                cmds.playbackOptions(query=True, maxTime=True)),
            "frameStartHandle": int(
                cmds.playbackOptions(query=True, animationStartTime=True)),
            "frameEndHandle": int(
                cmds.playbackOptions(query=True, animationEndTime=True))
        })
