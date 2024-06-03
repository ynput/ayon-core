from maya import cmds

from ayon_maya.api import (
    lib,
    plugin
)


class CreateYetiRig(plugin.MayaCreator):
    """Output for procedural plugin nodes ( Yeti / XGen / etc)"""

    identifier = "io.openpype.creators.maya.yetirig"
    label = "Yeti Rig"
    product_type = "yetiRig"
    icon = "usb"

    def create(self, product_name, instance_data, pre_create_data):

        with lib.undo_chunk():
            instance = super(CreateYetiRig, self).create(product_name,
                                                         instance_data,
                                                         pre_create_data)
            instance_node = instance.get("instance_node")

            self.log.info("Creating Rig instance set up ...")
            input_meshes = cmds.sets(name="input_SET", empty=True)
            cmds.sets(input_meshes, forceElement=instance_node)
