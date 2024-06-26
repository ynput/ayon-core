import os

import pyblish.api
from ayon_maya.api import plugin
from maya import cmds


class CollectMayaWorkspace(plugin.MayaContextPlugin):
    """Inject the current workspace into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Maya Workspace"


    def process(self, context):
        workspace = cmds.workspace(rootDirectory=True, query=True)
        if not workspace:
            # Project has not been set. Files will
            # instead end up next to the working file.
            workspace = cmds.workspace(dir=True, query=True)

        # Maya returns forward-slashes by default
        normalised = os.path.normpath(workspace)

        context.set_data('workspaceDir', value=normalised)
