from maya import cmds, mel

import pyblish.api
import ayon_core.hosts.maya.api.action
from ayon_core.pipeline.publish import (
    ValidateMeshOrder,
    PublishXmlValidationError,
    RepairAction,
    OptionalPyblishPluginMixin
)


def poly_cleanup(version=4,
                 meshes=None,
                 # Version 1
                 all_meshes=False,
                 select_only=False,
                 history_on=True,
                 quads=False,
                 nsided=False,
                 concave=False,
                 holed=False,
                 nonplanar=False,
                 zeroGeom=False,
                 zeroGeomTolerance=1e-05,
                 zeroEdge=False,
                 zeroEdgeTolerance=1e-05,
                 zeroMap=False,
                 zeroMapTolerance=1e-05,
                 # Version 2
                 shared_uvs=False,
                 non_manifold=False,
                 # Version 3
                 lamina=False,
                 # Version 4
                 invalid_components=False):
    """Wrapper around `polyCleanupArgList` mel command"""

    # Get all inputs named as `dict` to easily do conversions and formatting
    values = locals()

    # Convert booleans to 1 or 0
    for key in [
        "all_meshes",
        "select_only",
        "history_on",
        "quads",
        "nsided",
        "concave",
        "holed",
        "nonplanar",
        "zeroGeom",
        "zeroEdge",
        "zeroMap",
        "shared_uvs",
        "non_manifold",
        "lamina",
        "invalid_components",
    ]:
        values[key] = 1 if values[key] else 0

    cmd = (
        'polyCleanupArgList {version} {{ '
        '"{all_meshes}",'           # 0: All selectable meshes
        '"{select_only}",'          # 1: Only perform a selection
        '"{history_on}",'           # 2: Keep construction history
        '"{quads}",'                # 3: Check for quads polys
        '"{nsided}",'               # 4: Check for n-sides polys
        '"{concave}",'              # 5: Check for concave polys
        '"{holed}",'                # 6: Check for holed polys
        '"{nonplanar}",'            # 7: Check for non-planar polys
        '"{zeroGeom}",'             # 8: Check for 0 area faces
        '"{zeroGeomTolerance}",'    # 9: Tolerance for face areas
        '"{zeroEdge}",'             # 10: Check for 0 length edges
        '"{zeroEdgeTolerance}",'    # 11: Tolerance for edge length
        '"{zeroMap}",'              # 12: Check for 0 uv face area
        '"{zeroMapTolerance}",'     # 13: Tolerance for uv face areas
        '"{shared_uvs}",'           # 14: Unshare uvs that are shared
                                    #     across vertices
        '"{non_manifold}",'         # 15: Check for nonmanifold polys
        '"{lamina}",'               # 16: Check for lamina polys
        '"{invalid_components}"'    # 17: Remove invalid components
        ' }};'.format(**values)
    )

    mel.eval("source polyCleanupArgList")
    if not all_meshes and meshes:
        # Allow to specify meshes to run over by selecting them
        cmds.select(meshes, replace=True)
    mel.eval(cmd)


class CleanupMatchingPolygons(RepairAction):
    label = "Cleanup matching polygons"


def _as_report_list(values, prefix="- ", suffix="\n"):
    """Return list as bullet point list for a report"""
    if not values:
        return ""
    return prefix + (suffix + prefix).join(values)


class ValidateMeshNonManifold(pyblish.api.Validator,
                              OptionalPyblishPluginMixin):
    """Ensure that meshes don't have non-manifold edges or vertices

    To debug the problem on the meshes you can use Maya's modeling
    tool: "Mesh > Cleanup..."

    """

    order = ValidateMeshOrder
    hosts = ['maya']
    families = ['model']
    label = 'Mesh Non-Manifold Edges/Vertices'
    actions = [ayon_core.hosts.maya.api.action.SelectInvalidAction,
               CleanupMatchingPolygons]
    optional = True

    @staticmethod
    def get_invalid(instance):

        meshes = cmds.ls(instance, type='mesh', long=True)

        invalid = []
        for mesh in meshes:
            components = cmds.polyInfo(mesh,
                                       nonManifoldVertices=True,
                                       nonManifoldEdges=True)
            if components:
                invalid.extend(components)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)

        if invalid:
            # Report only the meshes instead of all component indices
            invalid_meshes = {
                component.split(".", 1)[0] for component in invalid
            }
            invalid_meshes = _as_report_list(sorted(invalid_meshes))

            raise PublishXmlValidationError(
                plugin=self,
                message=(
                    "Meshes found with non-manifold "
                    "edges/vertices:\n\n{0}".format(invalid_meshes)
                )
            )

    @classmethod
    def repair(cls, instance):
        invalid_components = cls.get_invalid(instance)
        if not invalid_components:
            cls.log.info("No invalid components found to cleanup.")
            return

        invalid_meshes = {
            component.split(".", 1)[0] for component in invalid_components
        }
        poly_cleanup(meshes=list(invalid_meshes),
                     select_only=True,
                     non_manifold=True)
