import nuke
import ayon_api

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_nuke.api.lib import maintained_selection
from ayon_nuke.api import (
    containerise,
    update_container,
    viewer_update_and_undo_stop
)


class AlembicModelLoader(load.LoaderPlugin):
    """
    This will load alembic model or anim into script.
    """

    product_types = {"model", "pointcache", "animation"}
    representations = {"*"}
    extensions = {"abc"}

    settings_category = "nuke"

    label = "Load Alembic"
    icon = "cube"
    color = "orange"
    node_color = "0x4ecd91ff"

    def load(self, context, name, namespace, data):
        # get main variables
        project_name = context["project"]["name"]
        version_entity = context["version"]

        version_attributes = version_entity["attrib"]
        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        fps = version_attributes.get("fps") or nuke.root()["fps"].getValue()

        namespace = namespace or context["folder"]["name"]
        object_name = "{}_{}".format(name, namespace)

        # prepare data for imprinting
        data_imprint = {
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"]
        }
        # add attributes from the version to imprint to metadata knob
        for k in ["source", "fps"]:
            data_imprint[k] = version_attributes[k]

        # getting file path
        file = self.filepath_from_context(context).replace("\\", "/")

        with maintained_selection():
            model_node = nuke.createNode(
                "ReadGeo2",
                "name {} file {} ".format(
                    object_name, file),
                inpanel=False
            )

            model_node.forceValidate()

            # Ensure all items are imported and selected.
            scene_view = model_node.knob('scene_view')
            scene_view.setImportedItems(scene_view.getAllItems())
            scene_view.setSelectedItems(scene_view.getAllItems())

            model_node["frame_rate"].setValue(float(fps))

            # workaround because nuke's bug is not adding
            # animation keys properly
            xpos = model_node.xpos()
            ypos = model_node.ypos()
            nuke.nodeCopy("%clipboard%")
            nuke.delete(model_node)
            nuke.nodePaste("%clipboard%")
            model_node = nuke.toNode(object_name)
            model_node.setXYpos(xpos, ypos)

        # color node by correct color by actual version
        self.node_version_color(project_name, version_entity, model_node)

        return containerise(
            node=model_node,
            name=name,
            namespace=namespace,
            context=context,
            loader=self.__class__.__name__,
            data=data_imprint)

    def update(self, container, context):
        """
            Called by Scene Inventory when look should be updated to current
            version.
            If any reference edits cannot be applied, eg. shader renamed and
            material not present, reference is unloaded and cleaned.
            All failed edits are highlighted to the user via message box.

        Args:
            container: object that has look to be updated
            context: (dict): relationship data to get proper
                                    representation from DB and persisted
                                    data in .json
        Returns:
            None
        """
        # Get version from io
        project_name = context["project"]["name"]
        version_entity = context["version"]
        repre_entity = context["representation"]

        # get corresponding node
        model_node = container["node"]

        # get main variables
        version_attributes = version_entity["attrib"]
        first = version_attributes.get("frameStart")
        last = version_attributes.get("frameEnd")
        fps = version_attributes.get("fps") or nuke.root()["fps"].getValue()

        # prepare data for imprinting
        data_imprint = {
            "representation": repre_entity["id"],
            "frameStart": first,
            "frameEnd": last,
            "version": version_entity["version"]
        }

        # add additional metadata from the version to imprint to Avalon knob
        for k in ["source", "fps"]:
            data_imprint[k] = version_attributes[k]

        # getting file path
        file = get_representation_path(repre_entity).replace("\\", "/")

        with maintained_selection():
            model_node['selected'].setValue(True)

            # collect input output dependencies
            dependencies = model_node.dependencies()
            dependent = model_node.dependent()

            model_node["frame_rate"].setValue(float(fps))
            model_node["file"].setValue(file)

            # Ensure all items are imported and selected.
            scene_view = model_node.knob('scene_view')
            scene_view.setImportedItems(scene_view.getAllItems())
            scene_view.setSelectedItems(scene_view.getAllItems())

            # workaround because nuke's bug is
            # not adding animation keys properly
            xpos = model_node.xpos()
            ypos = model_node.ypos()
            nuke.nodeCopy("%clipboard%")
            nuke.delete(model_node)

            # paste the node back and set the position
            nuke.nodePaste("%clipboard%")
            model_node = nuke.selectedNode()
            model_node.setXYpos(xpos, ypos)

            # link to original input nodes
            for i, input in enumerate(dependencies):
                model_node.setInput(i, input)
            # link to original output nodes
            for d in dependent:
                index = next((i for i, dpcy in enumerate(
                              d.dependencies())
                              if model_node is dpcy), 0)
                d.setInput(index, model_node)

        # color node by correct color by actual version
        self.node_version_color(project_name, version_entity, model_node)

        self.log.info(
            "updated to version: {}".format(version_entity["version"])
        )

        return update_container(model_node, data_imprint)

    def node_version_color(self, project_name, version_entity, node):
        """ Coloring a node by correct color by actual version"""

        last_version_entity = ayon_api.get_last_version_by_product_id(
            project_name, version_entity["productId"], fields={"id"}
        )

        # change color of node
        if version_entity["id"] == last_version_entity["id"]:
            color_value = self.node_color
        else:
            color_value = "0xd88467ff"
        node["tile_color"].setValue(int(color_value, 16))

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        node = nuke.toNode(container['objectName'])
        with viewer_update_and_undo_stop():
            nuke.delete(node)
