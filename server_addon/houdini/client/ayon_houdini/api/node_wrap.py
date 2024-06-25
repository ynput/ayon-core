from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext


def make_publishable(node):
    # TODO: Can we make this imprinting much faster? Unfortunately
    #  CreateContext initialization is very slow.
    host = registered_host()
    context = CreateContext(host)

    # Apply the instance creation to the node
    context.create(
        creator_identifier="io.ayon.creators.houdini.publish",
        variant=node.name(),
        pre_create_data={
            "node": node
        }
    )


# TODO: Move this choice of automatic 'imprint' to settings so studio can
#   configure which nodes should get automatically imprinted on creation
# TODO: Do not import and reload the creator plugin file
from ayon_houdini.plugins.create import create_generic
import importlib
importlib.reload(create_generic)
AUTO_CREATE_NODE_TYPES = set(
    create_generic.CreateHoudiniGeneric.node_type_product_types.keys()
)


def autocreate_publishable(node):
    # For now only consider RopNode
    if not isinstance(node, hou.RopNode):
        return

    node_type = node.type().name()
    if node_type in AUTO_CREATE_NODE_TYPES:
        make_publishable(node)
