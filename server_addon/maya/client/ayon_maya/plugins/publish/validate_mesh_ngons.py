import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ValidateMeshNgons(plugin.MayaInstancePlugin,
                        OptionalPyblishPluginMixin):
    """Ensure that meshes don't have ngons

    Ngon are faces with more than 4 sides.

    To debug the problem on the meshes you can use Maya's modeling
    tool: "Mesh > Cleanup..."

    """

    order = ValidateContentsOrder
    families = ["model"]
    label = "Mesh ngons"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = True

    description = (
        "## Meshes with NGONs Faces\n"
        "Detected meshes with NGON faces. **NGONS** are faces that "
        "with more than four sides.\n\n"
        "### How to repair?\n"
        "You can repair them by usings Maya's modeling tool Mesh > Cleanup.. "
        "and select to cleanup matching polygons for lamina faces."
    )

    @staticmethod
    def get_invalid(instance):

        meshes = cmds.ls(instance, type='mesh', long=True)

        # Get all faces
        faces = ['{0}.f[*]'.format(node) for node in meshes]

        # Skip meshes that for some reason have no faces, e.g. empty meshes
        faces = cmds.ls(faces)
        if not faces:
            return []

        # Filter to n-sided polygon faces (ngons)
        invalid = lib.polyConstraint(faces,
                                     t=0x0008,  # type=face
                                     size=3)    # size=nsided

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Meshes found with n-gons: {0}".format(invalid),
                description=self.description)
