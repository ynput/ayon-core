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

        settings = {"nodes": []}
        ox_shapes = cmds.ls(instance[:], shapes=True, long=True)
        for ox_shape in ox_shapes:
            # Get transform data
            parent = cmds.listRelatives(ox_shape, parent=True)[0]
            mesh_shape_data = {"name": parent, "cbId": lib.get_id(parent)}
            ox_cache_nodes = cmds.listConnections(
                ox_shape, destination=True, type="HairFromGuidesNode") or []
            if not ox_cache_nodes:
                continue
            # transfer cache file
            shape_data = {
                "shape": mesh_shape_data,
                "name": ox_shapes,
                "cbId": lib.get_id(ox_shape),
                "ox_nodes": ox_cache_nodes,
                "cache_file_attributes": ["{}.cacheFilePath".format(ox_node)
                                          for ox_node in ox_cache_nodes]
            }
            if shape_data["cbId"]:
                settings["nodes"].append(shape_data)
        instance.data["cachesettings"] = settings
