# -*- coding: utf-8 -*-
import os
import hou
from ayon_core.pipeline import (
    get_representation_path,
    AVALON_CONTAINER_ID
)
from ayon_houdini.api import (
    lib,
    pipeline,
    plugin
)

def get_avalon_container():
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

    return avalon_container


class HdaLoader(plugin.HoudiniLoader):
    """Load Houdini Digital Asset file."""

    product_types = {"hda"}
    label = "Load Hda"
    representations = {"hda"}
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        # Format file name, Houdini only wants forward slashes
        file_path = self.filepath_from_context(context)
        file_path = os.path.normpath(file_path)
        file_path = file_path.replace("\\", "/")

        # Create a unique name
        counter = 1
        namespace = namespace or context["folder"]["name"]
        formatted = "{}_{}".format(namespace, name) if namespace else name
        node_name = "{0}_{1:03d}".format(formatted, counter)

        hda_defs = hou.hda.definitionsInFile(file_path)
        if not hda_defs:
            raise RuntimeError ("No HDA definitions found!")

        hda_def = hda_defs[0]
        parent_node = self._create_dedicated_parent_node(hda_def)

        hou.hda.installFile(file_path)
        hda_node = parent_node.createNode(name, node_name)
        hda_node.moveToGoodPosition()

        # Set TAB Menu location interactively
        # This shouldn't be needed if the Tool Location is saved in the HDA.
        tool_name = hou.shelves.defaultToolName(
                hda_def.nodeTypeCategory().name(), hda_def.nodeTypeName())
        hou.shelves.tool(tool_name).setToolLocations(
            ("AYON/{}".format(context["project"]["name"]),))

        # Imprint it manually
        data = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": node_name,
            "namespace": namespace,
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
        }

        lib.imprint(hda_node, data)

        return hda_node

    def update(self, container, context):

        repre_entity = context["representation"]
        hda_node = container["node"]
        file_path = get_representation_path(repre_entity)
        file_path = file_path.replace("\\", "/")
        hou.hda.installFile(file_path)
        defs = hda_node.type().allInstalledDefinitions()
        def_paths = [d.libraryFilePath() for d in defs]
        new = def_paths.index(file_path)
        defs[new].setIsPreferred(True)
        hda_node.setParms({
            "representation": repre_entity["id"]
        })

    def remove(self, container):
        node = container["node"]
        parent = node.parent()
        node.destroy()

        if parent.type().category() == hou.objNodeTypeCategory():
            return

        # Remove parent if empty.
        if not parent.children():
            parent.destroy()

    def _create_dedicated_parent_node(self, hda_def):

        # Get the root node
        parent_node = get_avalon_container()
        node = None
        node_type = None
        if hda_def.nodeTypeCategory() == hou.objNodeTypeCategory():
            return parent_node
        elif hda_def.nodeTypeCategory() == hou.chopNodeTypeCategory():
            node_type, node_name = "chopnet", "MOTION"
        elif hda_def.nodeTypeCategory() == hou.cop2NodeTypeCategory():
            node_type, node_name = "cop2net", "IMAGES"
        elif hda_def.nodeTypeCategory() == hou.dopNodeTypeCategory():
            node_type, node_name = "dopnet", "DOPS"
        elif hda_def.nodeTypeCategory() == hou.ropNodeTypeCategory():
            node_type, node_name = "ropnet", "ROPS"
        elif hda_def.nodeTypeCategory() == hou.lopNodeTypeCategory():
            node_type, node_name = "lopnet", "LOPS"
        elif hda_def.nodeTypeCategory() == hou.sopNodeTypeCategory():
            node_type, node_name = "geo", "SOPS"
        elif hda_def.nodeTypeCategory() == hou.topNodeTypeCategory():
            node_type, node_name = "topnet", "TOPS"
        # TODO: Create a dedicated parent node based on Vop Node vex context.
        elif hda_def.nodeTypeCategory() == hou.vopNodeTypeCategory():
            node_type, node_name = "matnet", "MATSandVOPS"

        node = parent_node.node(node_name)
        if not node:
            node = parent_node.createNode(node_type, node_name)

        node.moveToGoodPosition()
        return node
