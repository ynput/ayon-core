import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateMeshOrder,
)
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ValidateMeshNonZeroEdgeLength(plugin.MayaInstancePlugin,
                                    OptionalPyblishPluginMixin):
    """Validate meshes don't have edges with a zero length.

    Based on Maya's polyCleanup 'Edges with zero length'.

    Note:
        This can be slow for high-res meshes.

    """

    order = ValidateMeshOrder
    families = ['model']
    label = 'Mesh Edge Length Non Zero'
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = True

    __tolerance = 1e-5

    @classmethod
    def get_invalid(cls, instance):
        """Return the invalid edges.

        Also see:

        http://help.autodesk.com/view/MAYAUL/2015/ENU/?guid=Mesh__Cleanup

        """

        meshes = cmds.ls(instance, type='mesh', long=True)
        if not meshes:
            return list()

        valid_meshes = []
        for mesh in meshes:
            num_vertices = cmds.polyEvaluate(mesh, vertex=True)

            if num_vertices == 0:
                cls.log.warning(
                    "Skipping \"{}\", cause it does not have any "
                    "vertices.".format(mesh)
                )
                continue

            valid_meshes.append(mesh)

        # Get all edges
        edges = ['{0}.e[*]'.format(node) for node in valid_meshes]

        # Filter by constraint on edge length
        invalid = lib.polyConstraint(edges,
                                     t=0x8000,  # type=edge
                                     length=1,
                                     lengthbound=(0, cls.__tolerance))

        return invalid

    def process(self, instance):
        """Process all meshes"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            label = "Meshes found with zero edge length"
            raise PublishValidationError(
                message="{}: {}".format(label, invalid),
                title=label,
                description="{}:\n- ".format(label) + "\n- ".join(invalid)
            )
