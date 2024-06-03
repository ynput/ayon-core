import os
from ayon_max.api import lib, maintained_selection
from ayon_max.api.lib import (
    unique_namespace,

)
from ayon_max.api.pipeline import (
    containerise,
    get_previous_loaded_object,
    update_custom_attribute_data,
    remove_container_data
)
from ayon_core.pipeline import get_representation_path, load


class TyCacheLoader(load.LoaderPlugin):
    """TyCache Loader."""

    product_types = {"tycache"}
    representations = {"tyc"}
    order = -8
    icon = "code-fork"
    color = "green"

    def load(self, context, name=None, namespace=None, data=None):
        """Load tyCache"""
        from pymxs import runtime as rt
        filepath = os.path.normpath(self.filepath_from_context(context))
        obj = rt.tyCache()
        obj.filename = filepath

        namespace = unique_namespace(
            name + "_",
            suffix="_",
        )
        obj.name = f"{namespace}:{obj.name}"

        return containerise(
            name, [obj], context,
            namespace, loader=self.__class__.__name__)

    def update(self, container, context):
        """update the container"""
        from pymxs import runtime as rt

        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        node = rt.GetNodeByName(container["instance_node"])
        node_list = get_previous_loaded_object(node)
        update_custom_attribute_data(node, node_list)
        with maintained_selection():
            for tyc in node_list:
                tyc.filename = path
        lib.imprint(container["instance_node"], {
            "representation": repre_entity["id"]
        })

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        """remove the container"""
        from pymxs import runtime as rt
        node = rt.GetNodeByName(container["instance_node"])
        remove_container_data(node)
