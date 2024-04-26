# -*- coding: utf-8 -*-
import maya.cmds as cmds

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.pipeline.load import get_representation_path_from_context
from ayon_core.hosts.maya.api.lib import (
    namespaced,
    unique_namespace
)
from ayon_core.hosts.maya.api.pipeline import containerise


class MayaUsdLoader(load.LoaderPlugin):
    """Read USD data in a Maya USD Proxy"""

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = {"usd", "usda", "usdc", "usdz", "abc"}

    label = "Load USD to Maya Proxy"
    order = -1
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Make sure we can load the plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        path = get_representation_path_from_context(context)

        # Create the shape
        cmds.namespace(addNamespace=namespace)
        with namespaced(namespace, new=False):
            transform = cmds.createNode("transform",
                                        name=name,
                                        skipSelect=True)
            proxy = cmds.createNode('mayaUsdProxyShape',
                                    name="{}Shape".format(name),
                                    parent=transform,
                                    skipSelect=True)

            cmds.connectAttr("time1.outTime", "{}.time".format(proxy))
            cmds.setAttr("{}.filePath".format(proxy), path, type="string")

            # By default, we force the proxy to not use a shared stage because
            # when doing so Maya will quite easily allow to save into the
            # loaded usd file. Since we are loading published files we want to
            # avoid altering them. Unshared stages also save their edits into
            # the workfile as an artist might expect it to do.
            cmds.setAttr("{}.shareStage".format(proxy), False)
            # cmds.setAttr("{}.shareStage".format(proxy), lock=True)

        nodes = [transform, proxy]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        # type: (dict, dict) -> None
        """Update container with specified representation."""
        node = container['objectName']
        assert cmds.objExists(node), "Missing container"

        members = cmds.sets(node, query=True) or []
        shapes = cmds.ls(members, type="mayaUsdProxyShape")

        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        for shape in shapes:
            cmds.setAttr("{}.filePath".format(shape), path, type="string")

        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        # Delete container and its contents
        if cmds.objExists(container['objectName']):
            members = cmds.sets(container['objectName'], query=True) or []
            cmds.delete([container['objectName']] + members)

        # Remove the namespace, if empty
        namespace = container['namespace']
        if cmds.namespace(exists=namespace):
            members = cmds.namespaceInfo(namespace, listNamespace=True)
            if not members:
                cmds.namespace(removeNamespace=namespace)
            else:
                self.log.warning("Namespace not deleted because it "
                                 "still has members: %s", namespace)
