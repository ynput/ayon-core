import json
from collections import OrderedDict
import nuke
import six
import ayon_api

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.hosts.nuke.api import (
    containerise,
    update_container,
    viewer_update_and_undo_stop
)


class LoadEffects(load.LoaderPlugin):
    """Loading colorspace soft effect exported from nukestudio"""

    product_types = {"effect"}
    representations = {"*"}
    extensions = {"json"}

    label = "Load Effects - nodes"
    order = 0
    icon = "cc"
    color = "white"
    ignore_attr = ["useLifetime"]


    def load(self, context, name, namespace, data):
        """
        Loading function to get the soft effects to particular read node

        Arguments:
            context (dict): context of version
            name (str): name of the version
            namespace (str): namespace name
            data (dict): compulsory attribute > not used

        Returns:
            nuke node: containerised nuke node object
        """
        # get main variables
        version_entity = context["version"]

        version_attributes = version_entity["attrib"]
        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        colorspace = version_attributes.get("colorSpace")

        workfile_first_frame = int(nuke.root()["first_frame"].getValue())
        namespace = namespace or context["folder"]["name"]
        object_name = "{}_{}".format(name, namespace)

        # prepare data for imprinting
        data_imprint = {
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"],
            "colorspaceInput": colorspace,
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

        # getting file path
        file = self.filepath_from_context(context).replace("\\", "/")

        # getting data from json file with unicode conversion
        with open(file, "r") as f:
            json_f = {self.byteify(key): self.byteify(value)
                      for key, value in json.load(f).items()}

        # get correct order of nodes by positions on track and subtrack
        nodes_order = self.reorder_nodes(json_f)

        # adding nodes to node graph
        # just in case we are in group lets jump out of it
        nuke.endGroup()

        GN = nuke.createNode(
            "Group",
            "name {}_1".format(object_name),
            inpanel=False
        )

        # adding content to the group node
        with GN:
            pre_node = nuke.createNode("Input")
            pre_node["name"].setValue("rgb")

            for ef_name, ef_val in nodes_order.items():
                node = nuke.createNode(ef_val["class"])
                for k, v in ef_val["node"].items():
                    if k in self.ignore_attr:
                        continue

                    try:
                        node[k].value()
                    except NameError as e:
                        self.log.warning(e)
                        continue

                    if isinstance(v, list) and len(v) > 4:
                        node[k].setAnimated()
                        for i, value in enumerate(v):
                            if isinstance(value, list):
                                for ci, cv in enumerate(value):
                                    node[k].setValueAt(
                                        cv,
                                        (workfile_first_frame + i),
                                        ci)
                            else:
                                node[k].setValueAt(
                                    value,
                                    (workfile_first_frame + i))
                    else:
                        node[k].setValue(v)
                node.setInput(0, pre_node)
                pre_node = node

            output = nuke.createNode("Output")
            output.setInput(0, pre_node)

        # try to find parent read node
        self.connect_read_node(GN, namespace, json_f["assignTo"])

        GN["tile_color"].setValue(int("0x3469ffff", 16))

        self.log.info("Loaded lut setup: `{}`".format(GN["name"].value()))

        return containerise(
            node=GN,
            name=name,
            namespace=namespace,
            context=context,
            loader=self.__class__.__name__,
            data=data_imprint)

    def update(self, container, context):
        """Update the Loader's path

        Nuke automatically tries to reset some variables when changing
        the loader's path to a new file. These automatic changes are to its
        inputs:

        """
        # get main variables
        # Get version from io
        project_name = context["project"]["name"]
        version_entity = context["version"]
        repre_entity = context["representation"]

        # get corresponding node
        GN = container["node"]

        file = get_representation_path(repre_entity).replace("\\", "/")

        version_attributes = version_entity["attrib"]
        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        colorspace = version_attributes.get("colorSpace")

        workfile_first_frame = int(nuke.root()["first_frame"].getValue())
        namespace = container["namespace"]

        data_imprint = {
            "representation": repre_entity["id"],
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"],
            "colorspaceInput": colorspace
        }

        for k in [
            "frameStart",
            "frameEnd",
            "handleStart",
            "handleEnd",
            "source",
            "author",
            "fps",
        ]:
            data_imprint[k] = version_attributes[k]

        # Update the imprinted representation
        update_container(
            GN,
            data_imprint
        )

        # getting data from json file with unicode conversion
        with open(file, "r") as f:
            json_f = {self.byteify(key): self.byteify(value)
                      for key, value in json.load(f).items()}

        # get correct order of nodes by positions on track and subtrack
        nodes_order = self.reorder_nodes(json_f)

        # adding nodes to node graph
        # just in case we are in group lets jump out of it
        nuke.endGroup()

        # adding content to the group node
        with GN:
            # first remove all nodes
            [nuke.delete(n) for n in nuke.allNodes()]

            # create input node
            pre_node = nuke.createNode("Input")
            pre_node["name"].setValue("rgb")

            for _, ef_val in nodes_order.items():
                node = nuke.createNode(ef_val["class"])
                for k, v in ef_val["node"].items():
                    if k in self.ignore_attr:
                        continue

                    try:
                        node[k].value()
                    except NameError as e:
                        self.log.warning(e)
                        continue

                    if isinstance(v, list) and len(v) > 4:
                        node[k].setAnimated()
                        for i, value in enumerate(v):
                            if isinstance(value, list):
                                for ci, cv in enumerate(value):
                                    node[k].setValueAt(
                                        cv,
                                        (workfile_first_frame + i),
                                        ci)
                            else:
                                node[k].setValueAt(
                                    value,
                                    (workfile_first_frame + i))
                    else:
                        node[k].setValue(v)
                node.setInput(0, pre_node)
                pre_node = node

            # create output node
            output = nuke.createNode("Output")
            output.setInput(0, pre_node)

        # try to find parent read node
        self.connect_read_node(GN, namespace, json_f["assignTo"])

        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )

        # change color of node
        if version_entity["id"] == last_version_entity["id"]:
            color_value = "0x3469ffff"
        else:
            color_value = "0xd84f20ff"

        GN["tile_color"].setValue(int(color_value, 16))

        self.log.info(
            "updated to version: {}".format(version_entity["version"])
        )

    def connect_read_node(self, group_node, namespace, product_name):
        """
        Finds read node and selects it

        Arguments:
            namespace (str): namespace name

        Returns:
            nuke node: node is selected
            None: if nothing found
        """
        search_name = "{0}_{1}".format(namespace, product_name)

        node = [
            n for n in nuke.allNodes(filter="Read")
            if search_name in n["file"].value()
        ]
        if len(node) > 0:
            rn = node[0]
        else:
            rn = None

        # Parent read node has been found
        # solving connections
        if rn:
            dep_nodes = rn.dependent()

            if len(dep_nodes) > 0:
                for dn in dep_nodes:
                    dn.setInput(0, group_node)

            group_node.setInput(0, rn)
            group_node.autoplace()

    def reorder_nodes(self, data):
        new_order = OrderedDict()
        trackNums = [v["trackIndex"] for k, v in data.items()
                     if isinstance(v, dict)]
        subTrackNums = [v["subTrackIndex"] for k, v in data.items()
                        if isinstance(v, dict)]

        for trackIndex in range(
                min(trackNums), max(trackNums) + 1):
            for subTrackIndex in range(
                    min(subTrackNums), max(subTrackNums) + 1):
                item = self.get_item(data, trackIndex, subTrackIndex)
                if item is not {}:
                    new_order.update(item)
        return new_order

    def get_item(self, data, trackIndex, subTrackIndex):
        return {key: val for key, val in data.items()
                if isinstance(val, dict)
                if subTrackIndex == val["subTrackIndex"]
                if trackIndex == val["trackIndex"]}

    def byteify(self, input):
        """
        Converts unicode strings to strings
        It goes through all dictionary

        Arguments:
            input (dict/str): input

        Returns:
            dict: with fixed values and keys

        """

        if isinstance(input, dict):
            return {self.byteify(key): self.byteify(value)
                    for key, value in input.items()}
        elif isinstance(input, list):
            return [self.byteify(element) for element in input]
        elif isinstance(input, six.text_type):
            return str(input)
        else:
            return input

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        node = container["node"]
        with viewer_update_and_undo_stop():
            nuke.delete(node)
