from maya import cmds

from ayon_maya.api import plugin


class CreateRig(plugin.MayaCreator):
    """Artist-friendly rig with controls to direct motion"""

    identifier = "io.openpype.creators.maya.rig"
    label = "Rig"
    product_type = "rig"
    icon = "wheelchair"

    def create(self, product_name, instance_data, pre_create_data):

        instance = super(CreateRig, self).create(product_name,
                                                 instance_data,
                                                 pre_create_data)

        instance_node = instance.get("instance_node")

        self.log.info("Creating Rig instance set up ...")
        # TODO：change name (_controls_SET -> _rigs_SET)
        controls = cmds.sets(name=product_name + "_controls_SET", empty=True)
        # TODO：change name (_out_SET -> _geo_SET)
        pointcache = cmds.sets(name=product_name + "_out_SET", empty=True)
        skeleton = cmds.sets(
            name=product_name + "_skeletonAnim_SET", empty=True)
        skeleton_mesh = cmds.sets(
            name=product_name + "_skeletonMesh_SET", empty=True)
        cmds.sets([controls, pointcache,
                   skeleton, skeleton_mesh], forceElement=instance_node)
