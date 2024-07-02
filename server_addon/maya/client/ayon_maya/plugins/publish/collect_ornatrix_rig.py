import os
from typing import List, Dict, Any
import pyblish.api
from ayon_core.pipeline.publish import KnownPublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


ORNATRIX_NODES = {
    "HairFromGuidesNode", "GuidesFromMeshNode",
    "MeshFromStrandsNode", "SurfaceCombNode"
}


class CollectOxRig(plugin.MayaInstancePlugin):
    """Collect all information of the Ornatrix Rig"""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Ornatrix Rig"
    families = ["oxrig"]

    def process(self, instance):
        ornatrix_nodes = cmds.ls(instance.data["setMembers"], long=True)
        self.log.debug(f"Getting ornatrix nodes: {ornatrix_nodes}")
        # Force frame range for yeti cache export for the rig
        # Collect any textures if used
        ornatrix_resources = []
        for node in ornatrix_nodes:
            # Get Yeti resources (textures)
            resources = self.get_texture_resources(node)
            ornatrix_resources.extend(resources)
        # avoid duplicate dictionary data
        instance.data["resources"] = [
            i for n, i in enumerate(ornatrix_resources)
            if i not in ornatrix_resources[n + 1:]
        ]
        self.log.debug("{}".format(instance.data["resources"]))

    def get_texture_resources(self, node: str) -> List[Dict[str, Any]]:
        resources = []
        node_shape = cmds.listRelatives(node, shapes=True)
        if not node_shape:
            return []

        ox_nodes = cmds.ls(
            cmds.listConnections(node_shape, destination=True) or [],
            type=ORNATRIX_NODES)

        ox_file_nodes = cmds.listConnections(ox_nodes, destination=False, type="file") or []
        if not ox_file_nodes:
            return []
        for file_node in ox_file_nodes:
            texture_attr = "{}.fileTextureName".format(file_node)
            texture = cmds.getAttr("{}.fileTextureName".format(file_node))
            files = []
            if os.path.isabs(texture):
                self.log.debug("Texture is absolute path, ignoring "
                               "image search paths for: %s" % texture)
                files = lib.search_textures(texture)
            else:
                root = os.environ["AYON_WORKDIR"]
                filepath = os.path.join(root, texture)
                files = lib.search_textures(filepath)
                if files:
                    continue

            if not files:
                raise KnownPublishError(
                    "No texture found for: %s "
                    "(searched: %s)" % (texture))

            item = {
                "node": node,
                "files": files,
                "source": texture,
                "texture_attribute": texture_attr
            }

            resources.append(item)

        return resources
