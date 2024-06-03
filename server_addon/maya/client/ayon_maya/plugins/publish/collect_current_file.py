import pyblish.api
from ayon_maya.api import plugin
from maya import cmds


class CollectCurrentFile(plugin.MayaContextPlugin):
    """Inject the current working file."""

    order = pyblish.api.CollectorOrder - 0.4
    label = "Maya Current File"

    def process(self, context):
        """Inject the current working file"""
        context.data['currentFile'] = cmds.file(query=True, sceneName=True)
