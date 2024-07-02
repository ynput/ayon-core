import json
import os
from ayon_core.pipeline import get_representation_path
from ayon_maya.api import lib
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from maya import cmds, mel


class OxCacheLoader(plugin.Loader):
    """Load Ornatrix Cache with one or more Ornatrix nodes"""

    product_types = {"oxcache", "oxrig"}
    representations = {"abc"}

    label = "Load Ornatrix Cache"
    order = -9
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):
        """Loads a .cachesettings file defining how to load .abc into
        HairGuideFromMesh nodes

        The .cachesettings file defines what the node names should be and also
        what "cbId" attribute they should receive to match the original source
        and allow published looks to also work for Ornatrix rigs and its caches.

        """
        # Ensure Ornatrix is loaded
        cmds.loadPlugin("Ornatrix", quiet=True)

        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)


        path = self.filepath_from_context(context)
        settings = self.read_settings(path)
        # read the fursettings
        nodes = []
        for setting in settings["nodes"]:
            nodes.extend(self.create_node(namespace, path, setting))

        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def remove(self, container):

        namespace = container["namespace"]
        nodes = container["nodes"]

        self.log.info("Removing '%s' from Maya.." % container["name"])

        nodes = cmds.ls(nodes, long=True)

        try:
            cmds.delete(nodes)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

    def update(self, container, context):
        repre_entity = context["representation"]
        nodes = container["nodes"]

        path = get_representation_path(repre_entity)
        for node in nodes:
            if cmds.ls(node, type="HairFromGuidesNode"):
                cmds.setAttr(f"{node}.cacheFilePath", path)

    def switch(self, container, context):
        self.update(container, context)

    # helper functions
    def create_namespace(self, folder_name):
        """Create a unique namespace
        Args:
            asset (dict): asset information

        """

        asset_name = "{}_".format(folder_name)
        prefix = "_" if asset_name[0].isdigit() else ""
        namespace = lib.unique_namespace(
            asset_name,
            prefix=prefix,
            suffix="_"
        )

        return namespace

    def create_node(self, namespace, filepath, node_settings):
        """Use the cachesettings to create a shape node which
        connects to HairFromGuidesNode with abc file cache.

        Args:
            namespace (str): namespace
            filepath (str): filepath
            node_settings (dict): node settings

        Returns:
            list: loaded nodes
        """
        nodes = []
        orig_guide_name = node_settings["name"]
        guide_name = "{}:{}".format(namespace, orig_guide_name)
        hair_guide_node = cmds.createNode("HairFromGuidesNode", name=guide_name)
        lib.set_id(hair_guide_node, node_settings["cbId"])
        cmds.setAttr(f"{hair_guide_node}.cacheFilePath", filepath, type="string")
        mel.eval("OxShowHairStackDialog();")
        nodes.extend([hair_guide_node])
        return nodes

    def read_settings(self, path):
        """Read the ornatrix-related parameters from the cachesettings.
        Args:
            path (str): filepath of cachesettings

        Returns:
            dict: setting attributes
        """
        path_no_ext, _ = os.path.splitext(path)
        settings_path = f"{path_no_ext}.cachesettings"
        with open(settings_path, "r") as fp:
            setting_attributes = json.load(fp)

        return setting_attributes
