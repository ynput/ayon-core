# -*- coding: utf-8 -*-
import os

import maya.cmds as cmds
from ayon_api import get_representation_by_id
from ayon_core.pipeline import get_representation_path
from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection, namespaced, unique_namespace
from ayon_maya.api.pipeline import containerise
from maya import mel


class MultiverseUsdLoader(plugin.Loader):
    """Read USD data in a Multiverse Compound"""

    product_types = {
        "model",
        "usd",
        "mvUsdComposition",
        "mvUsdOverride",
        "pointcache",
        "animation",
    }
    representations = {"usd", "usda", "usdc", "usdz", "abc"}

    label = "Load USD to Multiverse"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        path = self.filepath_from_context(context)

        # Make sure we can load the plugin
        cmds.loadPlugin("MultiverseForMaya", quiet=True)
        import multiverse

        # Create the shape
        with maintained_selection():
            cmds.namespace(addNamespace=namespace)
            with namespaced(namespace, new=False):
                shape = multiverse.CreateUsdCompound(path)
                transform = cmds.listRelatives(
                    shape, parent=True, fullPath=True)[0]

        nodes = [transform, shape]
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
        shapes = cmds.ls(members, type="mvUsdCompoundShape")
        assert shapes, "Cannot find mvUsdCompoundShape in container"

        project_name = context["project"]["name"]
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        prev_representation_id = cmds.getAttr("{}.representation".format(node))
        prev_representation = get_representation_by_id(project_name,
                                                       prev_representation_id)
        prev_path = os.path.normpath(prev_representation["attrib"]["path"])

        # Make sure we can load the plugin
        cmds.loadPlugin("MultiverseForMaya", quiet=True)
        import multiverse

        for shape in shapes:

            asset_paths = multiverse.GetUsdCompoundAssetPaths(shape)
            asset_paths = [os.path.normpath(p) for p in asset_paths]

            assert asset_paths.count(prev_path) == 1, \
                "Couldn't find matching path (or too many)"
            prev_path_idx = asset_paths.index(prev_path)

            asset_paths[prev_path_idx] = path

            multiverse.SetUsdCompoundAssetPaths(shape, asset_paths)

        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")
        mel.eval('refreshEditorTemplates;')

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
