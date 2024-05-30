import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api.lib import maintained_selection
from ayon_maya.api import plugin
from maya import cmds


class ValidateCycleError(plugin.MayaInstancePlugin,
                         OptionalPyblishPluginMixin):
    """Validate nodes produce no cycle errors."""

    order = ValidateContentsOrder + 0.05
    label = "Cycle Errors"
    hosts = ["maya"]
    families = ["rig"]
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Nodes produce a cycle error: {}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):

        with maintained_selection():
            cmds.select(instance[:], noExpand=True)
            plugs = cmds.cycleCheck(all=False,  # check selection only
                                    list=True)
            invalid = cmds.ls(plugs, objectsOnly=True, long=True)
            return invalid
