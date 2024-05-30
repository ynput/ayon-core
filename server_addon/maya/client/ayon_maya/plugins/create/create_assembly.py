from ayon_maya.api import plugin


class CreateAssembly(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.assembly"
    label = "Assembly"
    product_type = "assembly"
    icon = "cubes"
