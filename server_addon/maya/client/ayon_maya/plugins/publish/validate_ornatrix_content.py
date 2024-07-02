
import inspect
import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)

from ayon_maya.api import plugin
from maya import cmds


ORNATRIX_NODES = {
    "HairFromGuidesNode", "GuidesFromMeshNode",
    "MeshFromStrandsNode", "SurfaceCombNode"
}

class ValidateOrnatrixContent(plugin.MayaInstancePlugin,
                              OptionalPyblishPluginMixin):
    """Adheres to the content of 'oxrig' product type

    See `get_description` for more details.

    """

    order = ValidateContentsOrder
    families = ["oxrig"]
    label = "Validate Ornatrix Content"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    optional = False

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        nodes = instance.data["setMembers"]
        nodes_with_ornatrix = []
        for node in nodes:
            node_shape = cmds.listRelatives(node, shapes=True)
            if not node_shape:
                invalid.append(node)
            ox_nodes = cmds.ls(cmds.listConnections(
                node_shape, destination=True) or [], type=ORNATRIX_NODES)
            if ox_nodes:
                nodes_with_ornatrix.append(node)
        remainder = [node for node in nodes if node not in nodes_with_ornatrix]
        if remainder:
            invalid.extend(remainder)

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError(
                title="Ornatrix content is invalid",
                message="Ornatrix content is invalid. See log for more details.",
                description=self.get_description()
            )

    @classmethod
    def get_description(self):
        return inspect.cleandoc("""
            ### Ornatrix content is invalid

            Your oxrig instance does not adhere to the rules of a
            oxrig product type:
            - Must have the Ornatrix nodes connected to the shape
            of the mesh
        """)
