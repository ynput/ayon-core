from maya import cmds

from ayon_maya.api import plugin, lib


class CreateRig(plugin.MayaCreator):
    """Artist-friendly rig with controls to direct motion"""

    identifier = "io.openpype.creators.maya.rig"
    label = "Rig"
    product_type = "rig"
    icon = "wheelchair"
    set_suffixes = [
        "_controls_SET",
        "_out_SET",
        "_skeletonAnim_SET",
        "_skeletonMesh_SET"
    ]

    def create(self, product_name, instance_data, pre_create_data):

        instance = super(CreateRig, self).create(product_name,
                                                 instance_data,
                                                 pre_create_data)

        instance_node = instance.get("instance_node")

        self.log.info("Creating Rig instance set up ...")
        sets = []
        for suffix in self.set_suffixes:
            name = product_name + suffix
            cmds.sets(name=name, empty=True)
            sets.append(name)
        cmds.sets(sets, forceElement=instance_node)

        for node, id in lib.generate_ids(sets):
            lib.set_id(node, id, overwrite=True)

        return instance

    def remove_instances(self, instances):
        for instance in instances:
            nodes = [instance.data.get("instance_node")]
            for suffix in self.set_suffixes:
                nodes.append(instance.data.get("instance_node") + suffix)

            cmds.delete(cmds.ls(nodes))
            self._remove_instance_from_context(instance)
