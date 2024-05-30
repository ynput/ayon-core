import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ValidateRigJointsHidden(plugin.MayaInstancePlugin,
                              OptionalPyblishPluginMixin):
    """Validate all joints are hidden visually.

    This includes being hidden:
        - visibility off,
        - in a display layer that has visibility off,
        - having hidden parents or
        - being an intermediate object.

    """

    order = ValidateContentsOrder
    families = ['rig']
    label = "Joints Hidden"
    actions = [ayon_maya.api.action.SelectInvalidAction,
               RepairAction]
    optional = True

    @staticmethod
    def get_invalid(instance):
        joints = cmds.ls(instance, type='joint', long=True)
        return [j for j in joints if lib.is_visible(j, displayLayer=True)]

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError(
                "Visible joints found: {0}".format(invalid))

    @classmethod
    def repair(cls, instance):
        import maya.mel as mel
        mel.eval("HideJoints")
