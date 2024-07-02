from ayon_maya.api import plugin


class CreateOxRig(plugin.MayaCreator):
    """Output for Ornatrix nodes"""

    identifier = "io.openpype.creators.maya.oxrig"
    label = "Ornatrix Rig"
    product_type = "oxrig"
    icon = "usb"
