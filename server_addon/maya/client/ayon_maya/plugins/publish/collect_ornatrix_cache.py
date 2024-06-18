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
            transform_data = {"name": parent, "cbId": lib.get_id(parent)}
            ox_cache_nodes = [
                ox_node for ox_node in cmds.listConnections(ox_shape, destination=True)
                if cmds.nodeType(ox_node) == "HairFromGuidesNode"
            ]
            # transfer cache file
            shape_data = {
                "transform": transform_data,
                "name": ox_shapes,
                "cbId": lib.get_id(ox_shape),
                "ox_nodes": ox_cache_nodes,
                "cache_file_attribute": ["{}.cacheFilePath".format(ox_node)
                                        for ox_node in ox_cache_nodes]
            }
            settings["nodes"].append(shape_data)
        instance.data["cachesettings"] = settings
