import os
from ayon_core.pipeline import get_representation_path
from ayon_houdini.api import (
    pipeline,
    plugin
)


class AbcLoader(plugin.HoudiniLoader):
    """Load Alembic"""

    product_types = {"model", "animation", "pointcache", "gpuCache"}
    label = "Load Alembic"
    representations = {"*"}
    extensions = {"abc"}
    order = -10
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

        # Remove the file node, it only loads static meshes
        # Houdini 17 has removed the file node from the geo node
        file_node = container.node("file1")
        if file_node:
            file_node.destroy()

        # Create an alembic node (supports animation)
        alembic = container.createNode("alembic", node_name=node_name)
        alembic.setParms({"fileName": file_path})

        # Position nodes nicely
        container.moveToGoodPosition()
        container.layoutChildren()

        nodes = [container, alembic]

        return pipeline.containerise(
            node_name,
            namespace,
            nodes,
            context,
            self.__class__.__name__,
            suffix="",
        )

    def update(self, container, context):
        repre_entity = context["representation"]
        node = container["node"]
        try:
            alembic_node = next(
                n for n in node.children() if n.type().name() == "alembic"
            )
        except StopIteration:
            self.log.error("Could not find node of type `alembic`")
            return

        # Update the file path
        file_path = get_representation_path(repre_entity)
        file_path = file_path.replace("\\", "/")

        alembic_node.setParms({"fileName": file_path})

        # Update attribute
        node.setParms({"representation": repre_entity["id"]})

    def remove(self, container):

        node = container["node"]
        node.destroy()

    def switch(self, container, context):
        self.update(container, context)
