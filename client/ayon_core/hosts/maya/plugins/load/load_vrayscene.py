# -*- coding: utf-8 -*-
import maya.cmds as cmds  # noqa
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import (
    load,
    get_representation_path
)
from ayon_core.hosts.maya.api.lib import (
    maintained_selection,
    namespaced,
    unique_namespace
)
from ayon_core.hosts.maya.api.pipeline import containerise
from ayon_core.hosts.maya.api.plugin import get_load_color_for_product_type


class VRaySceneLoader(load.LoaderPlugin):
    """Load Vray scene"""

    product_types = {"vrayscene_layer"}
    representations = {"vrscene"}

    label = "Import VRay Scene"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        product_type = context["product"]["productType"]

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Ensure V-Ray for Maya is loaded.
        cmds.loadPlugin("vrayformaya", quiet=True)

        with maintained_selection():
            cmds.namespace(addNamespace=namespace)
            with namespaced(namespace, new=False):
                nodes, root_node = self.create_vray_scene(
                    name,
                    filename=self.filepath_from_context(context)
                )

        self[:] = nodes
        if not nodes:
            return

        # colour the group node
        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr("{0}.useOutlinerColor".format(root_node), 1)
            cmds.setAttr(
                "{0}.outlinerColor".format(root_node), red, green, blue
            )

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):

        node = container['objectName']
        assert cmds.objExists(node), "Missing container"

        members = cmds.sets(node, query=True) or []
        vraymeshes = cmds.ls(members, type="VRayScene")
        assert vraymeshes, "Cannot find VRayScene in container"

        repre_entity = context["representation"]
        filename = get_representation_path(repre_entity)

        for vray_mesh in vraymeshes:
            cmds.setAttr("{}.FilePath".format(vray_mesh),
                         filename,
                         type="string")

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def remove(self, container):

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

    def switch(self, container, context):
        self.update(container, context)

    def create_vray_scene(self, name, filename):
        """Re-create the structure created by VRay to support vrscenes

        Args:
            name(str): name of the asset

        Returns:
            nodes(list)
        """

        # Create nodes
        mesh_node_name = "VRayScene_{}".format(name)

        trans = cmds.createNode(
            "transform", name=mesh_node_name)
        vray_scene = cmds.createNode(
            "VRayScene", name="{}_VRSCN".format(mesh_node_name), parent=trans)
        mesh = cmds.createNode(
            "mesh", name="{}_Shape".format(mesh_node_name), parent=trans)

        cmds.connectAttr(
            "{}.outMesh".format(vray_scene), "{}.inMesh".format(mesh))

        cmds.setAttr("{}.FilePath".format(vray_scene), filename, type="string")

        # Lock the shape nodes so the user cannot delete these
        cmds.lockNode(mesh, lock=True)
        cmds.lockNode(vray_scene, lock=True)

        # Create important connections
        cmds.connectAttr("time1.outTime",
                         "{0}.inputTime".format(trans))

        # Connect mesh to initialShadingGroup
        cmds.sets([mesh], forceElement="initialShadingGroup")

        nodes = [trans, vray_scene, mesh]

        # Fix: Force refresh so the mesh shows correctly after creation
        cmds.refresh()

        return nodes, trans
