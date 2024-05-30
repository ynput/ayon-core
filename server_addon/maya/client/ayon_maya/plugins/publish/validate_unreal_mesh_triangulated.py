# -*- coding: utf-8 -*-
import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateMeshOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateUnrealMeshTriangulated(plugin.MayaInstancePlugin,
                                     OptionalPyblishPluginMixin):
    """Validate if mesh is made of triangles for Unreal Engine"""

    order = ValidateMeshOrder
    families = ["staticMesh"]
    label = "Mesh is Triangulated"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    active = False

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        meshes = cmds.ls(instance, type="mesh", long=True)
        for mesh in meshes:
            faces = cmds.polyEvaluate(mesh, face=True)
            tris = cmds.polyEvaluate(mesh, triangle=True)
            if faces != tris:
                invalid.append(mesh)

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError("Found meshes without triangles")
