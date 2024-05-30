# -*- coding: utf-8 -*-
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateUnrealUpAxis(plugin.MayaContextPlugin,
                           OptionalPyblishPluginMixin):
    """Validate if Z is set as up axis in Maya"""

    optional = True
    active = False
    order = ValidateContentsOrder
    families = ["staticMesh"]
    label = "Unreal Up-Axis check"
    actions = [RepairAction]

    def process(self, context):
        if not self.is_active(context.data):
            return

        if cmds.upAxis(q=True, axis=True) != "z":
            raise PublishValidationError(
                "Invalid axis set as up axis"
            )

    @classmethod
    def repair(cls, instance):
        cmds.upAxis(axis="z", rotateView=True)
