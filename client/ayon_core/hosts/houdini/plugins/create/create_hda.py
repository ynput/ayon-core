# -*- coding: utf-8 -*-
"""Creator plugin for creating publishable Houdini Digital Assets."""
import ayon_api

from ayon_core.pipeline import CreatorError
from ayon_core.hosts.houdini.api import plugin
import hou


class CreateHDA(plugin.HoudiniCreator):
    """Publish Houdini Digital Asset file."""

    identifier = "io.openpype.creators.houdini.hda"
    label = "Houdini Digital Asset (Hda)"
    product_type = "hda"
    icon = "gears"
    maintain_selection = False

    def _check_existing(self, folder_path, product_name):
        # type: (str, str) -> bool
        """Check if existing product name versions already exists."""
        # Get all products of the current folder
        project_name = self.project_name
        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path, fields={"id"}
        )
        product_entities = ayon_api.get_products(
            project_name, folder_ids={folder_entity["id"]}, fields={"name"}
        )
        existing_product_names_low = {
            product_entity["name"].lower()
            for product_entity in product_entities
        }
        return product_name.lower() in existing_product_names_low

    def create_instance_node(
        self, folder_path, node_name, parent, node_type="geometry"
    ):

        parent_node = hou.node("/obj")
        if self.selected_nodes:
            # if we have `use selection` enabled, and we have some
            # selected nodes ...
            subnet = parent_node.collapseIntoSubnet(
                self.selected_nodes,
                subnet_name="{}_subnet".format(node_name))
            subnet.moveToGoodPosition()
            to_hda = subnet
        else:
            to_hda = parent_node.createNode(
                "subnet", node_name="{}_subnet".format(node_name))
        if not to_hda.type().definition():
            # if node type has not its definition, it is not user
            # created hda. We test if hda can be created from the node.
            if not to_hda.canCreateDigitalAsset():
                raise CreatorError(
                    "cannot create hda from node {}".format(to_hda))

            hda_node = to_hda.createDigitalAsset(
                name=node_name,
                hda_file_name="$HIP/{}.hda".format(node_name)
            )
            hda_node.layoutChildren()
        elif self._check_existing(folder_path, node_name):
            raise CreatorError(
                ("product {} is already published with different HDA"
                 "definition.").format(node_name))
        else:
            hda_node = to_hda

        hda_node.setName(node_name)
        self.customize_node_look(hda_node)
        return hda_node

    def create(self, product_name, instance_data, pre_create_data):
        instance_data.pop("active", None)

        instance = super(CreateHDA, self).create(
            product_name,
            instance_data,
            pre_create_data)

        return instance

    def get_network_categories(self):
        return [
            hou.objNodeTypeCategory()
        ]
