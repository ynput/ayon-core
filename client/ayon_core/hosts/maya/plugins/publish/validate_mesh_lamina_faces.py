from maya import cmds

import pyblish.api
import ayon_core.hosts.maya.api.action
from ayon_core.pipeline.publish import (
    ValidateMeshOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)


class ValidateMeshLaminaFaces(pyblish.api.InstancePlugin,
                              OptionalPyblishPluginMixin):
    """Validate meshes don't have lamina faces.

    Lamina faces share all of their edges.

    """

    order = ValidateMeshOrder
    hosts = ['maya']
    families = ['model']
    label = 'Mesh Lamina Faces'
    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction]
    optional = True

    @staticmethod
    def get_invalid(instance):
        meshes = cmds.ls(instance, type='mesh', long=True)
        invalid = [mesh for mesh in meshes if
                   cmds.polyInfo(mesh, laminaFaces=True)]

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError(
                "Meshes found with lamina faces: {0}".format(invalid))
