import os

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import (
    load,
    get_representation_path
)
from ayon_core.hosts.maya.api.plugin import get_load_color_for_product_type
# TODO aiVolume doesn't automatically set velocity fps correctly, set manual?


class LoadVDBtoArnold(load.LoaderPlugin):
    """Load OpenVDB for Arnold in aiVolume"""

    product_types = {"vdbcache"}
    representations = {"vdb"}

    label = "Load VDB to Arnold"
    icon = "cloud"
    color = "orange"

    def load(self, context, name, namespace, data):

        from maya import cmds
        from ayon_core.hosts.maya.api.pipeline import containerise
        from ayon_core.hosts.maya.api.lib import unique_namespace

        product_type = context["product"]["productType"]

        # Check if the plugin for arnold is available on the pc
        try:
            cmds.loadPlugin("mtoa", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Root group
        label = "{}:{}".format(namespace, name)
        root = cmds.group(name=label, empty=True)

        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(root + ".useOutlinerColor", 1)
            cmds.setAttr(root + ".outlinerColor", red, green, blue)

        # Create VRayVolumeGrid
        grid_node = cmds.createNode("aiVolume",
                                    name="{}Shape".format(root),
                                    parent=root)

        path = self.filepath_from_context(context)
        self._set_path(grid_node,
                       path=path,
                       repre_entity=context["representation"])

        # Lock the shape node so the user can't delete the transform/shape
        # as if it was referenced
        cmds.lockNode(grid_node, lock=True)

        nodes = [root, grid_node]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):

        from maya import cmds

        repre_entity = context["representation"]

        path = get_representation_path(repre_entity)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        grid_nodes = cmds.ls(members, type="aiVolume", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._set_path(grid_nodes[0], path=path, repre_entity=repre_entity)

        # Update container representation
        cmds.setAttr(container["objectName"] + ".representation",
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):

        from maya import cmds

        # Get all members of the AYON container, ensure they are unlocked
        # and delete everything
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass

    @staticmethod
    def _set_path(grid_node,
                  path,
                  repre_entity):
        """Apply the settings for the VDB path to the aiVolume node"""
        from maya import cmds

        if not os.path.exists(path):
            raise RuntimeError("Path does not exist: %s" % path)

        is_sequence = "frame" in repre_entity["context"]
        cmds.setAttr(grid_node + ".useFrameExtension", is_sequence)

        # Set file path
        cmds.setAttr(grid_node + ".filename", path, type="string")
