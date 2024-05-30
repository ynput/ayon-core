import pyblish.api
from ayon_core.pipeline.publish import PublishValidationError
from ayon_maya.api import plugin
from maya import cmds


class ValidateVray(plugin.MayaInstancePlugin):
    """Validate general Vray setup."""

    order = pyblish.api.ValidatorOrder
    label = 'VRay'
    families = ["vrayproxy"]

    def process(self, instance):
        # Validate vray plugin is loaded.
        if not cmds.pluginInfo("vrayformaya", query=True, loaded=True):
            raise PublishValidationError("Vray plugin is not loaded.")
