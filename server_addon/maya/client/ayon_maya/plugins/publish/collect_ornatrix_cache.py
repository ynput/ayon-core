import pyblish.api
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class CollectOxCache(plugin.MayaInstancePlugin):
    """Collect all information of the Ornatrix caches"""

    order = pyblish.api.CollectorOrder + 0.45
    label = "Collect Ornatrix Cache"
    families = ["oxrig", "oxcache"]

    def process(self, instance):

        nodes = []
        ox_shapes = cmds.ls(instance[:], shapes=True, long=True)
        for ox_shape in ox_shapes:
            ox_shape_id = lib.get_id(ox_shape)
            if not ox_shape_id:
                continue
            ox_cache_nodes = cmds.listConnections(
                ox_shape, destination=True, type="HairFromGuidesNode") or []
            self.log.debug(f"{ox_shape}")
            if not ox_cache_nodes:
                continue
            # transfer cache file
            nodes.append({
                "name": ox_shape,
                "cbId": ox_shape_id,
                "ox_nodes": ox_cache_nodes,
                "cache_file_attributes": ["{}.cacheFilePath".format(ox_node)
                                          for ox_node in ox_cache_nodes]
            })
        instance.data["cachesettings"] = {"nodes": nodes}
        self.log.debug(f"{nodes}")