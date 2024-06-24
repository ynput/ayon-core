from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext


def make_publishable(node):
    # TODO: Can we make this imprinting much faster? Unfortunately
    #  CreateContext initialization is very slow.

    host = registered_host()
    context = CreateContext(host)

    variant = node.name()

    # Apply the instance creation to the node
    context.create(
        creator_identifier="io.ayon.creators.houdini.publish",
        variant=variant,
        pre_create_data={
            "node": node
        }
    )


# TODO: Move this choice of automatic 'imprint' to settings so studio can
#   configure which nodes should get automatically imprinted on creation
AUTO_CREATE_NODE_TYPES = {
    "alembic",
    "rop_alembic",
    "geometry",
    "rop_geometry",
    "filmboxfbx",
    "rop_fbx",
    "usd",
    "usd_rop",
    "usdexport",
    "comp",
    "opengl",
    "arnold",
    "labs::karma::2.0",
    "karma",
    "usdrender",
    "usdrender_rop",
    "vray_renderer",
}


def autocreate_publishable(node):
    node_type = node.type().name()
    if node_type in AUTO_CREATE_NODE_TYPES:
        make_publishable(node)
