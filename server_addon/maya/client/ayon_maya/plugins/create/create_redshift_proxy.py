# -*- coding: utf-8 -*-
"""Creator of Redshift proxy product types."""

from ayon_maya.api import plugin, lib
from ayon_core.lib import BoolDef


class CreateRedshiftProxy(plugin.MayaCreator):
    """Create instance of Redshift Proxy product."""

    identifier = "io.openpype.creators.maya.redshiftproxy"
    label = "Redshift Proxy"
    product_type = "redshiftproxy"
    icon = "gears"

    def get_instance_attr_defs(self):

        defs = [
            BoolDef("animation",
                    label="Export animation",
                    default=False)
        ]

        defs.extend(lib.collect_animation_defs())
        return defs
