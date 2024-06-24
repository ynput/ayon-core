

def make_publishable(node, product_type):
    # TODO: Can we make this imprinting much faster? Unfortunately
    #  CreateContext initialization is very slow.
    from ayon_core.pipeline import registered_host
    from ayon_core.pipeline.create import CreateContext

    host = registered_host()
    context = CreateContext(host)

    variant = node.name()

    # Apply the instance creation to the node
    context.create(
        creator_identifier="io.ayon.creators.houdini.publish",
        variant=variant,
        pre_create_data={
            "productType": product_type,
            "node": node
        }
    )


def autocreate_publishable(node):
    node_type = node.type().name()

    # TODO: Move this choice of automatic 'imprint' to settings so studio can
    #   configure which nodes should get automatically imprinted on creation
    mapping = {
        # Pointcache
        "alembic": "pointcache",
        "rop_alembic": "pointcache",
        "geometry": "pointcache",
        "rop_geometry": "pointcache",
        # FBX
        "filmboxfbx": "fbx",
        "rop_fbx": "fbx",
        # USD
        "usd": "usd",
        "usd_rop": "usd",
        "usdexport": "usd",
        "comp": "imagesequence",
        "opengl": "review",
        # Render
        "arnold": "render",
        "labs::karma::2.0": "render",
        "karma": "render",
        "usdrender": "render",
        "usdrender_rop": "render",
        "vray_renderer": "render"
    }
    product_type = mapping.get(node_type, None)
    if product_type:
        make_publishable(node, product_type)