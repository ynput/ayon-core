import os

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import (
    load,
    get_representation_path
)
from ayon_core.hosts.maya.api.plugin import get_load_color_for_product_type


class LoadVDBtoRedShift(load.LoaderPlugin):
    """Load OpenVDB in a Redshift Volume Shape

    Note that the RedshiftVolumeShape is created without a RedshiftVolume
    shader assigned. To get the Redshift volume to render correctly assign
    a RedshiftVolume shader (in the Hypershade) and set the density, scatter
    and emission channels to the channel names of the volumes in the VDB file.

    """

    product_types = {"vdbcache"}
    representations = ["vdb"]

    label = "Load VDB to RedShift"
    icon = "cloud"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        from maya import cmds
        from ayon_core.hosts.maya.api.pipeline import containerise
        from ayon_core.hosts.maya.api.lib import unique_namespace

        product_type = context["product"]["productType"]

        # Check if the plugin for redshift is available on the pc
        try:
            cmds.loadPlugin("redshift4maya", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

        # Check if viewport drawing engine is Open GL Core (compat)
        render_engine = None
        compatible = "OpenGL"
        if cmds.optionVar(exists="vp2RenderingEngine"):
            render_engine = cmds.optionVar(query="vp2RenderingEngine")

        if not render_engine or not render_engine.startswith(compatible):
            raise RuntimeError("Current scene's settings are incompatible."
                               "See Preferences > Display > Viewport 2.0 to "
                               "set the render engine to '%s<type>'"
                               % compatible)

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Root group
        label = "{}:{}".format(namespace, name)
        root = cmds.createNode("transform", name=label)

        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(root + ".useOutlinerColor", 1)
            cmds.setAttr(root + ".outlinerColor", red, green, blue)

        # Create VR
        volume_node = cmds.createNode("RedshiftVolumeShape",
                                      name="{}RVSShape".format(label),
                                      parent=root)

        self._set_path(volume_node,
                       path=self.filepath_from_context(context),
                       representation=context["representation"])

        nodes = [root, volume_node]
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
        grid_nodes = cmds.ls(members, type="RedshiftVolumeShape", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._set_path(grid_nodes[0], path=path, representation=repre_entity)

        # Update container representation
        cmds.setAttr(container["objectName"] + ".representation",
                     repre_entity["id"],
                     type="string")

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

    def switch(self, container, context):
        self.update(container, context)

    @staticmethod
    def _set_path(grid_node,
                  path,
                  representation):
        """Apply the settings for the VDB path to the RedshiftVolumeShape"""
        from maya import cmds

        if not os.path.exists(path):
            raise RuntimeError("Path does not exist: %s" % path)

        is_sequence = "frame" in representation["context"]
        cmds.setAttr(grid_node + ".useFrameExtension", is_sequence)

        # Set file path
        cmds.setAttr(grid_node + ".fileName", path, type="string")
