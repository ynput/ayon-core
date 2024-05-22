# -*- coding: utf-8 -*-
"""Creator for Unreal Static Meshes."""
from ayon_core.hosts.maya.api import plugin, lib
from maya import cmds  # noqa


class CreateUnrealStaticMesh(plugin.MayaCreator):
    """Unreal Static Meshes with collisions."""

    identifier = "io.openpype.creators.maya.unrealstaticmesh"
    label = "Unreal - Static Mesh"
    product_type = "staticMesh"
    icon = "cube"

    # Defined in settings
    collision_prefixes = []

    def get_dynamic_data(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name,
        instance
    ):
        """
        The default product name templates for Unreal include {asset} and thus
        we should pass that along as dynamic data.
        """
        dynamic_data = super(CreateUnrealStaticMesh, self).get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            instance
        )
        dynamic_data["asset"] = folder_entity["name"]
        return dynamic_data

    def create(self, product_name, instance_data, pre_create_data):

        with lib.undo_chunk():
            instance = super(CreateUnrealStaticMesh, self).create(
                product_name, instance_data, pre_create_data)
            instance_node = instance.get("instance_node")

            # We reorganize the geometry that was originally added into the
            # set into either 'collision_SET' or 'geometry_SET' based on the
            # collision_prefixes from project settings
            members = cmds.sets(instance_node, query=True)
            cmds.sets(clear=instance_node)

            geometry_set = cmds.sets(name="geometry_SET", empty=True)
            collisions_set = cmds.sets(name="collisions_SET", empty=True)

            cmds.sets([geometry_set, collisions_set],
                      forceElement=instance_node)

            members = cmds.ls(members, long=True) or []
            children = cmds.listRelatives(members, allDescendents=True,
                                          fullPath=True) or []
            transforms = cmds.ls(members + children, type="transform")
            for transform in transforms:

                if not cmds.listRelatives(transform,
                                          type="shape",
                                          noIntermediate=True):
                    # Exclude all transforms that have no direct shapes
                    continue

                if self.has_collision_prefix(transform):
                    cmds.sets(transform, forceElement=collisions_set)
                else:
                    cmds.sets(transform, forceElement=geometry_set)

    def has_collision_prefix(self, node_path):
        """Return whether node name of path matches collision prefix.

        If the node name matches the collision prefix we add it to the
        `collisions_SET` instead of the `geometry_SET`.

        Args:
            node_path (str): Maya node path.

        Returns:
            bool: Whether the node should be considered a collision mesh.

        """
        node_name = node_path.rsplit("|", 1)[-1]
        for prefix in self.collision_prefixes:
            if node_name.startswith(prefix):
                return True
        return False
