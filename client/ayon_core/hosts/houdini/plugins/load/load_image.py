import os
import re

from ayon_core.pipeline import (
    load,
    get_representation_path,
    AVALON_CONTAINER_ID,
)
from ayon_core.hosts.houdini.api import lib, pipeline

import hou


def get_image_avalon_container():
    """The COP2 files must be in a COP2 network.

    So we maintain a single entry point within AVALON_CONTAINERS,
    just for ease of use.

    """

    path = pipeline.AVALON_CONTAINERS
    avalon_container = hou.node(path)
    if not avalon_container:
        # Let's create avalon container secretly
        # but make sure the pipeline still is built the
        # way we anticipate it was built, asserting it.
        assert path == "/obj/AVALON_CONTAINERS"

        parent = hou.node("/obj")
        avalon_container = parent.createNode(
            "subnet", node_name="AVALON_CONTAINERS"
        )

    image_container = hou.node(path + "/IMAGES")
    if not image_container:
        image_container = avalon_container.createNode(
            "cop2net", node_name="IMAGES"
        )
        image_container.moveToGoodPosition()

    return image_container


class ImageLoader(load.LoaderPlugin):
    """Load images into COP2"""

    product_types = {
        "imagesequence",
        "review",
        "render",
        "plate",
        "image",
        "online",
    }
    label = "Load Image (COP2)"
    representations = ["*"]
    order = -10

    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        # Format file name, Houdini only wants forward slashes
        path = self.filepath_from_context(context)
        path = self.format_path(path, representation=context["representation"])

        # Get the root node
        parent = get_image_avalon_container()

        # Define node name
        namespace = namespace if namespace else context["folder"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        node = parent.createNode("file", node_name=node_name)
        node.moveToGoodPosition()

        parms = {"filename1": path}
        parms.update(self.get_colorspace_parms(context["representation"]))

        node.setParms(parms)

        # Imprint it manually
        data = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": node_name,
            "namespace": namespace,
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
        }

        # todo: add folder="Avalon"
        lib.imprint(node, data)

        return node

    def update(self, container, context):
        repre_entity = context["representation"]
        node = container["node"]

        # Update the file path
        file_path = get_representation_path(repre_entity)
        file_path = self.format_path(file_path, repre_entity)

        parms = {
            "filename1": file_path,
            "representation": repre_entity["id"],
        }

        parms.update(self.get_colorspace_parms(repre_entity))

        # Update attributes
        node.setParms(parms)

    def remove(self, container):

        node = container["node"]

        # Let's clean up the IMAGES COP2 network
        # if it ends up being empty and we deleted
        # the last file node. Store the parent
        # before we delete the node.
        parent = node.parent()

        node.destroy()

        if not parent.children():
            parent.destroy()

    @staticmethod
    def format_path(path, representation):
        """Format file path correctly for single image or sequence."""
        if not os.path.exists(path):
            raise RuntimeError("Path does not exist: %s" % path)

        ext = os.path.splitext(path)[-1]

        is_sequence = bool(representation["context"].get("frame"))
        # The path is either a single file or sequence in a folder.
        if not is_sequence:
            filename = path
        else:
            filename = re.sub(r"(.*)\.(\d+){}$".format(re.escape(ext)),
                              "\\1.$F4{}".format(ext),
                              path)

            filename = os.path.join(path, filename)

        filename = os.path.normpath(filename)
        filename = filename.replace("\\", "/")

        return filename

    def get_colorspace_parms(self, representation: dict) -> dict:
        """Return the color space parameters.

        Returns the values for the colorspace parameters on the node if there
        is colorspace data on the representation.

        Arguments:
            representation (dict): The representation entity.

        Returns:
            dict: Parm to value mapping if colorspace data is defined.

        """
        # Using OCIO colorspace on COP2 File node is only supported in Hou 20+
        major, _, _ = hou.applicationVersion()
        if major < 20:
            return {}

        data = representation.get("data", {}).get("colorspaceData", {})
        if not data:
            return {}

        colorspace = data["colorspace"]
        if colorspace:
            return {
                "colorspace": 3,  # Use OpenColorIO
                "ocio_space": colorspace
            }

    def switch(self, container, representation):
        self.update(container, representation)
