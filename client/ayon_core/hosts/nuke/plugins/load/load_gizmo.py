import nuke
import ayon_api

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.hosts.nuke.api.lib import (
    maintained_selection,
    get_avalon_knob_data,
    set_avalon_knob_data,
    swap_node_with_dependency,
)
from ayon_core.hosts.nuke.api import (
    containerise,
    update_container,
    viewer_update_and_undo_stop
)


class LoadGizmo(load.LoaderPlugin):
    """Loading nuke Gizmo"""

    product_types = {"gizmo"}
    representations = {"*"}
    extensions = {"nk"}

    label = "Load Gizmo"
    order = 0
    icon = "dropbox"
    color = "white"
    node_color = "0x75338eff"

    def load(self, context, name, namespace, data):
        """
        Loading function to get Gizmo into node graph

        Arguments:
            context (dict): context of version
            name (str): name of the version
            namespace (str): namespace name
            data (dict): compulsory attribute > not used

        Returns:
            nuke node: containerized nuke node object
        """

        # get main variables
        version_entity = context["version"]
        version_attributes = version_entity["attrib"]

        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        colorspace = version_attributes.get("colorSpace")

        namespace = namespace or context["folder"]["name"]
        object_name = "{}_{}".format(name, namespace)

        # prepare data for imprinting
        data_imprint = {
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"],
            "colorspaceInput": colorspace
        }

        # add attributes from the version to imprint to metadata knob
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

        # adding nodes to node graph
        # just in case we are in group lets jump out of it
        nuke.endGroup()

        with maintained_selection():
            # add group from nk
            nuke.nodePaste(file)

            group_node = nuke.selectedNode()

            group_node["name"].setValue(object_name)

            return containerise(
                node=group_node,
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

        version_attributes = version_entity["attrib"]

        # get corresponding node
        group_node = container["node"]

        file = get_representation_path(repre_entity).replace("\\", "/")

        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        colorspace = version_attributes.get("colorSpace")

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
            "fps"
        ]:
            data_imprint[k] = version_attributes[k]

        # capture pipeline metadata
        avalon_data = get_avalon_knob_data(group_node)

        # adding nodes to node graph
        # just in case we are in group lets jump out of it
        nuke.endGroup()

        with maintained_selection([group_node]):
            # insert nuke script to the script
            nuke.nodePaste(file)
            # convert imported to selected node
            new_group_node = nuke.selectedNode()
            # swap nodes with maintained connections
            with swap_node_with_dependency(
                    group_node, new_group_node) as node_name:
                new_group_node["name"].setValue(node_name)
                # set updated pipeline metadata
                set_avalon_knob_data(new_group_node, avalon_data)

        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )

        # change color of node
        if version_entity["id"] == last_version_entity["id"]:
            color_value = self.node_color
        else:
            color_value = "0xd88467ff"

        new_group_node["tile_color"].setValue(int(color_value, 16))

        self.log.info(
            "updated to version: {}".format(version_entity["name"])
        )

        return update_container(new_group_node, data_imprint)

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        node = container["node"]
        with viewer_update_and_undo_stop():
            nuke.delete(node)
