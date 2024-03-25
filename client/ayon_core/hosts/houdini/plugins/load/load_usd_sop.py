import os

from ayon_core.pipeline import load
from ayon_core.hosts.houdini.api import pipeline


class SopUsdImportLoader(load.LoaderPlugin):
    """Load USD to SOPs via `usdimport`"""

    label = "Load USD to SOPs"
    product_types = {"*"}
    representations = ["usd"]
    order = -6
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):
        import hou

        # Format file name, Houdini only wants forward slashes
        file_path = self.filepath_from_context(context)
        file_path = os.path.normpath(file_path)
        file_path = file_path.replace("\\", "/")

        # Get the root node
        obj = hou.node("/obj")

        # Define node name
        namespace = namespace if namespace else context["folder"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        # Create a new geo node
        container = obj.createNode("geo", node_name=node_name)

        # Create a usdimport node
        usdimport = container.createNode("usdimport", node_name=node_name)
        usdimport.setParms({"filepath1": file_path})

        # Set new position for unpack node else it gets cluttered
        nodes = [container, usdimport]

        return pipeline.containerise(
            node_name,
            namespace,
            nodes,
            context,
            self.__class__.__name__,
            suffix="",
        )

    def update(self, container, context):

        node = container["node"]
        try:
            usdimport_node = next(
                n for n in node.children() if n.type().name() == "usdimport"
            )
        except StopIteration:
            self.log.error("Could not find node of type `usdimport`")
            return

        # Update the file path
        file_path = self.filepath_from_context(context)
        file_path = file_path.replace("\\", "/")

        usdimport_node.setParms({"filepath1": file_path})

        # Update attribute
        node.setParms({"representation": context["representation"]["id"]})

    def remove(self, container):

        node = container["node"]
        node.destroy()

    def switch(self, container, representation):
        self.update(container, representation)
