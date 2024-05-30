from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateLayout(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.layout"
    label = "Layout"
    product_type = "layout"
    icon = "cubes"

    def get_instance_attr_defs(self):

        return [
            BoolDef("groupLoadedAssets",
                    label="Group Loaded Assets",
                    tooltip="Enable this when you want to publish group of "
                            "loaded asset",
                    default=False)
        ]
