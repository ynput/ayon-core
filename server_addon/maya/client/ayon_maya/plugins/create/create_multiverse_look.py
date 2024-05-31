from ayon_maya.api import plugin
from ayon_core.lib import (
    BoolDef,
    EnumDef
)


class CreateMultiverseLook(plugin.MayaCreator):
    """Create Multiverse Look"""

    identifier = "io.openpype.creators.maya.mvlook"
    label = "Multiverse Look"
    product_type = "mvLook"
    icon = "cubes"

    def get_instance_attr_defs(self):

        return [
            EnumDef("fileFormat",
                    label="File Format",
                    tooltip="USD export file format",
                    items=["usda", "usd"],
                    default="usda"),
            BoolDef("publishMipMap",
                    label="Publish MipMap",
                    default=True),
        ]
