import maya.cmds as cmds

from ayon_core.hosts.maya.api.pipeline import containerise
from ayon_core.hosts.maya.api.lib import unique_namespace
from ayon_core.pipeline import (
    load,
    get_representation_path
)
from ayon_core.settings import get_project_settings
from ayon_core.hosts.maya.api.plugin import get_load_color_for_product_type


class GpuCacheLoader(load.LoaderPlugin):
    """Load Alembic as gpuCache"""

    product_types = {"model", "animation", "proxyAbc", "pointcache"}
    representations = ["abc", "gpu_cache"]

    label = "Load Gpu Cache"
    order = -5
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        cmds.loadPlugin("gpuCache", quiet=True)

        # Root group
        label = "{}:{}".format(namespace, name)
        root = cmds.group(name=label, empty=True)

        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type("model", settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(root + ".useOutlinerColor", 1)
            cmds.setAttr(
                root + ".outlinerColor", red, green, blue
            )

        # Create transform with shape
        transform_name = label + "_GPU"
        transform = cmds.createNode("transform", name=transform_name,
                                    parent=root)
        cache = cmds.createNode("gpuCache",
                                parent=transform,
                                name="{0}Shape".format(transform_name))

        # Set the cache filepath
        path = self.filepath_from_context(context)
        cmds.setAttr(cache + '.cacheFileName', path, type="string")
        cmds.setAttr(cache + '.cacheGeomPath', "|", type="string")    # root

        # Lock parenting of the transform and cache
        cmds.lockNode([transform, cache], lock=True)

        nodes = [root, transform, cache]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)

        # Update the cache
        members = cmds.sets(container['objectName'], query=True)
        caches = cmds.ls(members, type="gpuCache", long=True)

        assert len(caches) == 1, "This is a bug"

        for cache in caches:
            cmds.setAttr(cache + ".cacheFileName", path, type="string")

        cmds.setAttr(container["objectName"] + ".representation",
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass
