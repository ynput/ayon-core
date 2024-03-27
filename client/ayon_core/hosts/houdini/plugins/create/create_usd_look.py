# -*- coding: utf-8 -*-
"""Creator plugin for creating USD looks with textures."""
import inspect

from ayon_core.hosts.houdini.api import plugin
from ayon_core.pipeline import CreatedInstance

import hou


class CreateUSDLook(plugin.HoudiniCreator):
    """Universal Scene Description Look"""

    identifier = "io.openpype.creators.houdini.usd.look"
    label = "Look"
    product_type = "look"
    icon = "gears"
    enabled = True
    description = "Create USD Look"

    def create(self, product_name, instance_data, pre_create_data):

        instance_data.pop("active", None)
        instance_data.update({"node_type": "usd"})

        instance = super(CreateUSDLook, self).create(
            product_name,
            instance_data,
            pre_create_data)  # type: CreatedInstance

        instance_node = hou.node(instance.get("instance_node"))

        parms = {
            "lopoutput": "$HIP/pyblish/{}.usd".format(product_name),
            "enableoutputprocessor_simplerelativepaths": False,

            # Set the 'default prim' by default to the asset being published to
            "defaultprim": '/`chs("asset")`',
        }

        if self.selected_nodes:
            parms["loppath"] = self.selected_nodes[0].path()

        instance_node.setParms(parms)

        # Lock any parameters in this list
        to_lock = [
            "fileperframe",
            # Lock some Avalon attributes
            "family",
            "id",
        ]
        self.lock_parameters(instance_node, to_lock)

    def get_detail_description(self):
        return inspect.cleandoc("""Publish looks in USD data.

        From the Houdini Solaris context (LOPs) this will publish the look for
        an asset as a USD file with the used textures.

        Any assets used by the look will be relatively remapped to the USD
        file and integrated into the publish as `resources`.

        """)

    def get_network_categories(self):
        return [
            hou.ropNodeTypeCategory(),
            hou.lopNodeTypeCategory()
        ]

    def get_publish_families(self):
        return ["usd", "look", "usdrop"]
