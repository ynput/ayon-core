import os
import re

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.hosts.houdini.api import pipeline


class VdbLoader(load.LoaderPlugin):
    """Load VDB"""

    product_types = {"vdbcache"}
    label = "Load VDB"
    representations = {"vdb"}
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        import hou

        # Get the root node
        obj = hou.node("/obj")

        # Define node name
        namespace = namespace if namespace else context["folder"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        # Create a new geo node
        container = obj.createNode("geo", node_name=node_name)

        # Remove the file node, it only loads static meshes
        # Houdini 17 has removed the file node from the geo node
        file_node = container.node("file1")
        if file_node:
            file_node.destroy()

        # Explicitly create a file node
        file_node = container.createNode("file", node_name=node_name)
        path = self.filepath_from_context(context)
        file_node.setParms(
            {"file": self.format_path(path, context["representation"])})

        # Set display on last node
        file_node.setDisplayFlag(True)

        nodes = [container, file_node]
        self[:] = nodes

        return pipeline.containerise(
            node_name,
            namespace,
            nodes,
            context,
            self.__class__.__name__,
            suffix="",
        )

    @staticmethod
    def format_path(path, representation):
        """Format file path correctly for single vdb or vdb sequence."""
        if not os.path.exists(path):
            raise RuntimeError("Path does not exist: %s" % path)

        is_sequence = bool(representation["context"].get("frame"))
        # The path is either a single file or sequence in a folder.
        if not is_sequence:
            filename = path
        else:
            filename = re.sub(r"(.*)\.(\d+)\.vdb$", "\\1.$F4.vdb", path)

            filename = os.path.join(path, filename)

        filename = os.path.normpath(filename)
        filename = filename.replace("\\", "/")

        return filename

    def update(self, container, context):
        repre_entity = context["representation"]
        node = container["node"]
        try:
            file_node = next(
                n for n in node.children() if n.type().name() == "file"
            )
        except StopIteration:
            self.log.error("Could not find node of type `alembic`")
            return

        # Update the file path
        file_path = get_representation_path(repre_entity)
        file_path = self.format_path(file_path, repre_entity)

        file_node.setParms({"file": file_path})

        # Update attribute
        node.setParms({"representation": repre_entity["id"]})

    def remove(self, container):

        node = container["node"]
        node.destroy()

    def switch(self, container, context):
        self.update(container, context)
