# -*- coding: utf-8 -*-

from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api.action import SelectInvalidAction
from ayon_maya.api import plugin
from maya import cmds


class ValidateSkeletalMeshTriangulated(plugin.MayaInstancePlugin):
    """Validates that the geometry has been triangulated."""

    order = ValidateContentsOrder
    families = ["skeletalMesh"]
    label = "Skeletal Mesh Triangulated"
    optional = True
    actions = [
        SelectInvalidAction,
        RepairAction
    ]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "The following objects needs to be triangulated: "
                "{}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):
        geo = instance.data.get("geometry")

        invalid = []

        for obj in cmds.listRelatives(
                cmds.ls(geo), allDescendents=True, fullPath=True):
            n_triangles = cmds.polyEvaluate(obj, triangle=True)
            n_faces = cmds.polyEvaluate(obj, face=True)

            if not (isinstance(n_triangles, int) and isinstance(n_faces, int)):
                continue

            # We check if the number of triangles is equal to the number of
            # faces for each transform node.
            # If it is, the object is triangulated.
            if cmds.objectType(obj, i="transform") and n_triangles != n_faces:
                invalid.append(obj)

        return invalid

    @classmethod
    def repair(cls, instance):
        for node in cls.get_invalid(instance):
            cmds.polyTriangulate(node)
