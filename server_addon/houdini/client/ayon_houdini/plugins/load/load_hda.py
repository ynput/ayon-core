# -*- coding: utf-8 -*-
import os
from ayon_core.pipeline import get_representation_path
from ayon_core.pipeline.load import LoadError
from ayon_houdini.api import (
    pipeline,
    plugin
)


class HdaLoader(plugin.HoudiniLoader):
    """Load Houdini Digital Asset file."""

    product_types = {"hda"}
    label = "Load Hda"
    representations = {"hda"}
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

        namespace = namespace or context["folder"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        hou.hda.installFile(file_path)

        # Get the type name from the HDA definition.
        hda_defs = hou.hda.definitionsInFile(file_path)
        if not hda_defs:
            raise LoadError(f"No HDA definitions found in file: {file_path}")

        type_name = hda_defs[0].nodeTypeName()
        hda_node = obj.createNode(type_name, node_name)

        self[:] = [hda_node]

        return pipeline.containerise(
            node_name,
            namespace,
            [hda_node],
            context,
            self.__class__.__name__,
            suffix="",
        )

    def update(self, container, context):
        import hou

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
        node.destroy()
