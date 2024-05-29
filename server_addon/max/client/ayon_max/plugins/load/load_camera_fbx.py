import os

from ayon_max.api import lib
from ayon_max.api.lib import (
    unique_namespace,
    get_namespace,
    object_transform_set
)
from ayon_max.api.pipeline import (
    containerise,
    get_previous_loaded_object,
    update_custom_attribute_data,
    remove_container_data
)
from ayon_core.pipeline import get_representation_path, load


class FbxLoader(load.LoaderPlugin):
    """Fbx Loader."""

    product_types = {"camera"}
    representations = {"fbx"}
    order = -9
    icon = "code-fork"
    color = "white"

    def load(self, context, name=None, namespace=None, data=None):
        from pymxs import runtime as rt
        filepath = self.filepath_from_context(context)
        filepath = os.path.normpath(filepath)
        rt.FBXImporterSetParam("Animation", True)
        rt.FBXImporterSetParam("Camera", True)
        rt.FBXImporterSetParam("AxisConversionMethod", True)
        rt.FBXImporterSetParam("Mode", rt.Name("create"))
        rt.FBXImporterSetParam("Preserveinstances", True)
        rt.ImportFile(
            filepath,
            rt.name("noPrompt"),
            using=rt.FBXIMP)

        namespace = unique_namespace(
            name + "_",
            suffix="_",
        )
        selections = rt.GetCurrentSelection()

        for selection in selections:
            selection.name = f"{namespace}:{selection.name}"

        return containerise(
            name, selections, context,
            namespace, loader=self.__class__.__name__)

    def update(self, container, context):
        from pymxs import runtime as rt

        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        node_name = container["instance_node"]
        node = rt.getNodeByName(node_name)
        namespace, _ = get_namespace(node_name)

        node_list = get_previous_loaded_object(node)
        rt.Select(node_list)
        prev_fbx_objects = rt.GetCurrentSelection()
        transform_data = object_transform_set(prev_fbx_objects)
        for prev_fbx_obj in prev_fbx_objects:
            if rt.isValidNode(prev_fbx_obj):
                rt.Delete(prev_fbx_obj)

        rt.FBXImporterSetParam("Animation", True)
        rt.FBXImporterSetParam("Camera", True)
        rt.FBXImporterSetParam("Mode", rt.Name("merge"))
        rt.FBXImporterSetParam("AxisConversionMethod", True)
        rt.FBXImporterSetParam("Preserveinstances", True)
        rt.ImportFile(
            path, rt.name("noPrompt"), using=rt.FBXIMP)
        current_fbx_objects = rt.GetCurrentSelection()
        fbx_objects = []
        for fbx_object in current_fbx_objects:
            fbx_object.name = f"{namespace}:{fbx_object.name}"
            fbx_objects.append(fbx_object)
            fbx_transform = f"{fbx_object.name}.transform"
            if fbx_transform in transform_data.keys():
                fbx_object.pos = transform_data[fbx_transform] or 0
                fbx_object.scale = transform_data[
                    f"{fbx_object.name}.scale"] or 0

        update_custom_attribute_data(node, fbx_objects)
        lib.imprint(container["instance_node"], {
            "representation": repre_entity["id"]
        })

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        from pymxs import runtime as rt

        node = rt.GetNodeByName(container["instance_node"])
        remove_container_data(node)
