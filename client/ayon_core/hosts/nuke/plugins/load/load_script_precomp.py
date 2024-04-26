import nuke
import ayon_api

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.hosts.nuke.api.lib import get_avalon_knob_data
from ayon_core.hosts.nuke.api import (
    containerise,
    update_container,
    viewer_update_and_undo_stop
)


class LinkAsGroup(load.LoaderPlugin):
    """Copy the published file to be pasted at the desired location"""

    product_types = {"workfile", "nukenodes"}
    representations = {"*"}
    extensions = {"nk"}

    label = "Load Precomp"
    order = 0
    icon = "file"
    color = "#cc0000"

    def load(self, context, name, namespace, data):
        # for k, v in context.items():
        #     log.info("key: `{}`, value: {}\n".format(k, v))
        version_entity = context["version"]

        version_attributes = version_entity["attrib"]
        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        colorspace = version_attributes.get("colorSpace")

        # Fallback to folder name when namespace is None
        if namespace is None:
            namespace = context["folder"]["name"]

        file = self.filepath_from_context(context).replace("\\", "/")
        self.log.info("file: {}\n".format(file))

        data_imprint = {
            "startingFrame": first,
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"]
        }
        # add additional metadata from the version to imprint to Avalon knob
        for k in [
            "frameStart",
            "frameEnd",
            "handleStart",
            "handleEnd",
            "source",
            "author",
            "fps"
        ]:
            data_imprint[k] = version_attributes[k]

        # group context is set to precomp, so back up one level.
        nuke.endGroup()

        # P = nuke.nodes.LiveGroup("file {}".format(file))
        P = nuke.createNode(
            "Precomp",
            "file {}".format(file),
            inpanel=False
        )

        # Set colorspace defined in version data
        self.log.info("colorspace: {}\n".format(colorspace))

        P["name"].setValue("{}_{}".format(name, namespace))
        P["useOutput"].setValue(True)

        with P:
            # iterate through all nodes in group node and find pype writes
            writes = [n.name() for n in nuke.allNodes()
                      if n.Class() == "Group"
                      if get_avalon_knob_data(n)]

            if writes:
                # create panel for selecting output
                panel_choices = " ".join(writes)
                panel_label = "Select write node for output"
                p = nuke.Panel("Select Write Node")
                p.addEnumerationPulldown(
                    panel_label, panel_choices)
                p.show()
                P["output"].setValue(p.value(panel_label))

        P["tile_color"].setValue(0xff0ff0ff)

        return containerise(
                     node=P,
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

        project_name = context["project"]["name"]
        version_entity = context["version"]
        repre_entity = context["representation"]

        root = get_representation_path(repre_entity).replace("\\", "/")

        # Get start frame from version data

        version_attributes = version_entity["attrib"]
        updated_dict = {
            "representation": repre_entity["id"],
            "frameEnd": version_attributes.get("frameEnd"),
            "version": version_entity["version"],
            "colorspace": version_attributes.get("colorSpace"),
            "source": version_attributes.get("source"),
            "fps": version_attributes.get("fps"),
            "author": version_attributes.get("author")
        }

        # Update the imprinted representation
        update_container(
            node,
            updated_dict
        )

        node["file"].setValue(root)

        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )
        # change color of node
        if version_entity["id"] == last_version_entity["id"]:
            color_value = "0xff0ff0ff"
        else:
            color_value = "0xd84f20ff"
        node["tile_color"].setValue(int(color_value, 16))

        self.log.info(
            "updated to version: {}".format(version_entity["version"])
        )

    def remove(self, container):
        node = container["node"]
        with viewer_update_and_undo_stop():
            nuke.delete(node)
