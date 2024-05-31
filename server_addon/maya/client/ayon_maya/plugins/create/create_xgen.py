from ayon_maya.api import plugin


class CreateXgen(plugin.MayaCreator):
    """Xgen"""

    identifier = "io.openpype.creators.maya.xgen"
    label = "Xgen"
    product_type = "xgen"
    icon = "pagelines"
