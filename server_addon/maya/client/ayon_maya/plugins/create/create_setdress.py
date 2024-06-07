from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateSetDress(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.setdress"
    label = "Set Dress"
    product_type = "setdress"
    icon = "cubes"
    default_variants = ["Main", "Anim"]

    def get_instance_attr_defs(self):
        return [
            BoolDef("exactSetMembersOnly",
                    label="Exact Set Members Only",
                    default=True)
        ]
