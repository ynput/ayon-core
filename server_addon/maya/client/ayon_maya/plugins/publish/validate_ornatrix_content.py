
import inspect
import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)

from ayon_maya.api import plugin
from maya import cmds


class ValidateModelContent(plugin.MayaInstancePlugin,
                           OptionalPyblishPluginMixin):
    """Adheres to the content of 'oxrig' product type

    See `get_description` for more details.

    """

    order = ValidateContentsOrder
    families = ["oxrig"]
    label = "Ornatrix Content"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    optional = False

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        nodes = instance.data["setMembers"]
        ox_nodes = []
        for node in nodes:
            node_shape = cmds.listRelatives(node, shapes=True)
            if not node_shape:
                invalid.extend(node_shape)
            all_nodes_connections = cmds.listConnections(node_shape, destination=True)
            ox_nodes = cmds.ls(all_nodes_connections or [], type=ORNATRIX_NODES)
        remainder = nodes.difference(ox_nodes)
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
        return inspect.cleandoc(f"""
            ### Ornatrix content is invalid

            Your oxrig instance does not adhere to the rules of a
            oxrig product type:
            - Must have the Ornatrix nodes connected to the shape
            of the mesh
        """)
