from ayon_core.pipeline import load
from ayon_core.hosts.houdini.api.lib import find_active_network

import hou


class LOPLoadAssetLoader(load.LoaderPlugin):

    product_types = {"*"}
    label = "Load Asset (LOPs)"
    representations = ["usd", "abc", "usda", "usdc"]
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        # Define node name
        namespace = namespace if namespace else context["asset"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        # Create node
        network = find_active_network(
            category=hou.lopNodeTypeCategory(),
            default="/stage"
        )
        node = network.createNode("ayon::lop_import", node_name=node_name)
        node.moveToGoodPosition()

        # Set representation id
        representation_id = str(context["representation"]["_id"])
        parm = node.parm("representation")
        parm.set(representation_id)
        parm.pressButton()  # trigger callbacks

        nodes = [node]
        self[:] = nodes

    def update(self, container, representation):
        node = container["node"]

        representation_id = str(representation["_id"])
        parm = node.parm("representation")
        parm.set(representation_id)
        parm.pressButton()  # trigger callbacks

    def remove(self, container):
        node = container["node"]
        node.destroy()

    def switch(self, container, representation):
        self.update(container, representation)
