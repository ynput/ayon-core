import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateMeshOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateMeshLaminaFaces(plugin.MayaInstancePlugin,
                              OptionalPyblishPluginMixin):
    """Validate meshes don't have lamina faces.

    Lamina faces share all of their edges.

    """

    order = ValidateMeshOrder
    families = ['model']
    label = 'Mesh Lamina Faces'
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = True

    description = (
        "## Meshes with Lamina Faces\n"
        "Detected meshes with lamina faces. <b>Lamina faces</b> are faces "
        "that share all of their edges and thus are merged together on top of "
        "each other.\n\n"
        "### How to repair?\n"
        "You can repair them by using Maya's modeling tool `Mesh > Cleanup..` "
        "and select to cleanup matching polygons for lamina faces."
    )

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
                "Meshes found with lamina faces: {0}".format(invalid),
                description=self.description)
