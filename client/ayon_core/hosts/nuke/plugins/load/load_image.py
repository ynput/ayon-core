import nuke

import qargparse
import ayon_api

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.hosts.nuke.api.lib import (
    get_imageio_input_colorspace
)
from ayon_core.hosts.nuke.api import (
    containerise,
    update_container,
    viewer_update_and_undo_stop
)
from ayon_core.lib.transcoding import (
    IMAGE_EXTENSIONS
)


class LoadImage(load.LoaderPlugin):
    """Load still image into Nuke"""

    product_types = {
        "render2d",
        "source",
        "plate",
        "render",
        "prerender",
        "review",
        "image",
    }
    representations = {"*"}
    extensions = set(
        ext.lstrip(".") for ext in IMAGE_EXTENSIONS
    )

    label = "Load Image"
    order = -10
    icon = "image"
    color = "white"

    # Loaded from settings
    representations_include = []

    node_name_template = "{class_name}_{ext}"

    options = [
        qargparse.Integer(
            "frame_number",
            label="Frame Number",
            default=int(nuke.root()["first_frame"].getValue()),
            min=1,
            max=999999,
            help="What frame is reading from?"
        )
    ]

    @classmethod
    def get_representations(cls):
        return cls.representations_include or cls.representations

    def load(self, context, name, namespace, options):
        self.log.info("__ options: `{}`".format(options))
        frame_number = options.get(
            "frame_number", int(nuke.root()["first_frame"].getValue())
        )

        version_entity = context["version"]
        version_attributes = version_entity["attrib"]
        repre_entity = context["representation"]
        repre_id = repre_entity["id"]

        self.log.debug(
            "Representation id `{}` ".format(repre_id))

        last = first = int(frame_number)

        # Fallback to folder name when namespace is None
        if namespace is None:
            namespace = context["folder"]["name"]

        file = self.filepath_from_context(context)

        if not file:
            self.log.warning(
                "Representation id `{}` is failing to load".format(repre_id))
            return

        file = file.replace("\\", "/")

        frame = repre_entity["context"].get("frame")
        if frame:
            padding = len(frame)
            file = file.replace(
                frame,
                format(frame_number, "0{}".format(padding)))

        read_name = self._get_node_name(context)

        # Create the Loader with the filename path set
        with viewer_update_and_undo_stop():
            r = nuke.createNode(
                "Read",
                "name {}".format(read_name),
                inpanel=False
            )

            r["file"].setValue(file)

            # Set colorspace defined in version data
            colorspace = version_entity["attrib"].get("colorSpace")
            if colorspace:
                r["colorspace"].setValue(str(colorspace))

            preset_clrsp = get_imageio_input_colorspace(file)

            if preset_clrsp is not None:
                r["colorspace"].setValue(preset_clrsp)

            r["origfirst"].setValue(first)
            r["first"].setValue(first)
            r["origlast"].setValue(last)
            r["last"].setValue(last)

            # add attributes from the version to imprint metadata knob
            colorspace = version_attributes["colorSpace"]
            data_imprint = {
                "frameStart": first,
                "frameEnd": last,
                "version": version_entity["version"],
                "colorspace": colorspace,
            }
            for k in ["source", "author", "fps"]:
                data_imprint[k] = version_attributes.get(k, str(None))

            r["tile_color"].setValue(int("0x4ecd25ff", 16))

            return containerise(r,
                                name=name,
                                namespace=namespace,
                                context=context,
                                loader=self.__class__.__name__,
                                data=data_imprint)

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        """Update the Loader's path

        Nuke automatically tries to reset some variables when changing
        the loader's path to a new file. These automatic changes are to its
        inputs:

        """
        node = container["node"]
        frame_number = node["first"].value()

        assert node.Class() == "Read", "Must be Read"

        project_name = context["project"]["name"]
        version_entity = context["version"]
        repre_entity = context["representation"]

        repr_cont = repre_entity["context"]

        file = get_representation_path(repre_entity)

        if not file:
            repre_id = repre_entity["id"]
            self.log.warning(
                "Representation id `{}` is failing to load".format(repre_id))
            return

        file = file.replace("\\", "/")

        frame = repr_cont.get("frame")
        if frame:
            padding = len(frame)
            file = file.replace(
                frame,
                format(frame_number, "0{}".format(padding)))

        # Get start frame from version data
        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )

        last = first = int(frame_number)

        # Set the global in to the start frame of the sequence
        node["file"].setValue(file)
        node["origfirst"].setValue(first)
        node["first"].setValue(first)
        node["origlast"].setValue(last)
        node["last"].setValue(last)

        version_attributes = version_entity["attrib"]
        updated_dict = {
            "representation": repre_entity["id"],
            "frameStart": str(first),
            "frameEnd": str(last),
            "version": str(version_entity["version"]),
            "colorspace": version_attributes.get("colorSpace"),
            "source": version_attributes.get("source"),
            "fps": str(version_attributes.get("fps")),
            "author": version_attributes.get("author")
        }

        # change color of node
        if version_entity["id"] == last_version_entity["id"]:
            color_value = "0x4ecd25ff"
        else:
            color_value = "0xd84f20ff"
        node["tile_color"].setValue(int(color_value, 16))

        # Update the imprinted representation
        update_container(node, updated_dict)
        self.log.info("updated to version: {}".format(
            version_entity["version"]
        ))

    def remove(self, container):
        node = container["node"]
        assert node.Class() == "Read", "Must be Read"

        with viewer_update_and_undo_stop():
            nuke.delete(node)

    def _get_node_name(self, context):
        folder_entity = context["folder"]
        product_name = context["product"]["name"]
        repre_entity = context["representation"]

        folder_name = folder_entity["name"]
        repre_cont = repre_entity["context"]
        name_data = {
            "folder": {
                "name": folder_name,
            },
            "product": {
                "name": product_name,
            },
            "asset": folder_name,
            "subset": product_name,
            "representation": repre_entity["name"],
            "ext": repre_cont["representation"],
            "id": repre_entity["id"],
            "class_name": self.__class__.__name__
        }

        return self.node_name_template.format(**name_data)
