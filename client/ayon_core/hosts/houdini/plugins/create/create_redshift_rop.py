# -*- coding: utf-8 -*-
"""Creator plugin to create Redshift ROP."""
import hou  # noqa

from ayon_core.pipeline import CreatorError
from ayon_core.hosts.houdini.api import plugin
from ayon_core.lib import EnumDef, BoolDef


class CreateRedshiftROP(plugin.HoudiniCreator):
    """Redshift ROP"""

    identifier = "io.openpype.creators.houdini.redshift_rop"
    label = "Redshift ROP"
    product_type = "redshift_rop"
    icon = "magic"
    ext = "exr"
    multi_layered_mode = "1"

    # Default to split export and render jobs
    split_render = True

    def create(self, product_name, instance_data, pre_create_data):

        instance_data.pop("active", None)
        instance_data.update({"node_type": "Redshift_ROP"})
        # Add chunk size attribute
        instance_data["chunkSize"] = 10
        # Submit for job publishing
        instance_data["farm"] = pre_create_data.get("farm")
        # Transfer settings from pre create to instance
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        data_to_transfer = ["farm", "split_render",
                            "image_format", "multi_layered_mode"]
        for key in data_to_transfer:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]
        instance = super(CreateRedshiftROP, self).create(
            product_name,
            instance_data,
            pre_create_data)

        instance_node = hou.node(instance.get("instance_node"))

        basename = instance_node.name()

        # Also create the linked Redshift IPR Rop
        try:
            ipr_rop = instance_node.parent().createNode(
                "Redshift_IPR", node_name=f"{basename}_IPR"
            )
        except hou.OperationFailed as e:
            raise CreatorError(
                (
                    "Cannot create Redshift node. Is Redshift "
                    "installed and enabled?"
                )
            ) from e

        # Move it to directly under the Redshift ROP
        ipr_rop.setPosition(instance_node.position() + hou.Vector2(0, -1))

        # Set the linked rop to the Redshift ROP
        ipr_rop.parm("linked_rop").set(instance_node.path())

        filepath = "{renders_dir}{product_name}/{product_name}.{fmt}".format(
                renders_dir=hou.text.expandString("$HIP/pyblish/renders/"),
                product_name=product_name,
                fmt="$AOV.$F4.{ext}".format(ext=pre_create_data.get("image_format"))
            )

        rs_filepath = "{export_dir}{product_name}/{product_name}.$F4.rs".format(
            export_dir=hou.text.expandString("$HIP/pyblish/rs/"),
            product_name=product_name
        )

        parms = {
            # Render frame range
            "trange": 1,
            # Redshift ROP settings
            "RS_outputFileNamePrefix": filepath,
            "RS_outputBeautyAOVSuffix": "beauty",
            "RS_archive_file": rs_filepath
        }

        camera = None
        if self.selected_nodes:
            # set up the render camera from the selected node
            for node in self.selected_nodes:
                if node.type().name() == "cam":
                    camera = node.path()
                    parms["RS_renderCamera"] = camera or ""

        instance_node.setParms(parms)

        # Set parameters that depends on the value of creator data.
        self.update_node_parameters(instance_node, pre_create_data)

        # Lock some Avalon attributes
        to_lock = ["productType", "id"]
        self.lock_parameters(instance_node, to_lock)

    def remove_instances(self, instances):
        for instance in instances:
            node = instance.data.get("instance_node")

            ipr_node = hou.node(f"{node}_IPR")
            if ipr_node:
                ipr_node.destroy()

        return super(CreateRedshiftROP, self).remove_instances(instances)

    @staticmethod
    def update_node_parameters(node, creator_attributes):
        """update node parameters according to creator attributes.

        Implementation of `HoudiniCreator.update_node_parameters`.
        This method is used in `HoudiniCreator.update_instances`
            which triggered on `save` action in the publisher.
        It's used to update the parameters of instance node
            according to the values of creator_attributes.

        Args:
            node(hou.Node): Houdini node to apply changes to.
            creator_attributes(dict): Dictionary of creator attributes.
        """

        ext = creator_attributes.get("image_format")
        ext_format_index = {"exr": 0, "tif": 1, "jpg": 2, "png": 3}

        parms = {
            "RS_outputFileFormat": ext_format_index[ext],
            "RS_archive_enable": creator_attributes.get("split_render"),
            "farm": creator_attributes.get("farm")
        }

        if ext == "exr":
            multi_layered_mode = creator_attributes.get("multi_layered_mode")
            multipart = multi_layered_mode != "2"
            parms["RS_outputMultilayerMode"] = multi_layered_mode
            parms["RS_aovMultipart"] = multipart

        node.setParms(parms)

    @staticmethod
    def read_node_data(node):
        """Read node data from node parameters.

        Implementation of `HoudiniCreator.read_node_data`.
        This method is used in `HoudiniCreator.collect_instances`
          which triggered on `refresh` action in the publisher.
        It's used to compute ayon attributes (mainly creator attributes)
          based on the values of the parameters of instance node.
        It should invert the logic of `update_node_parameters`

        Args:
            node(hou.Node): Houdini node to read changes from.

        Returns:
            settings (Optional[dict[str, Any]]):
        """
        ext_format_index = {0: "exr", 1: "tif", 2: "jpg", 3:"png"}

        node_data = {
            "creator_attributes": {
                "multi_layered_mode": node.evalParm("RS_outputMultilayerMode"),
                "farm": node.evalParm("farm"),
                "split_render": node.evalParm("RS_archive_enable"),
                "image_format": ext_format_index[node.evalParm("RS_outputFileFormat")],
            }
        }

        return node_data

    def get_instance_attr_defs(self):
        image_format_enum = [
            "exr", "tif", "jpg", "png",
        ]
        multi_layered_mode = {
            "1": "No Multi-Layered EXR File",
            "2": "Full Multi-Layered EXR File"
        }

        return [
            BoolDef("farm",
                    label="Submitting to Farm",
                    default=True),
            BoolDef("split_render",
                    label="Split export and render jobs",
                    default=self.split_render),
            EnumDef("image_format",
                    image_format_enum,
                    default=self.ext,
                    label="Image Format Options"),
            EnumDef("multi_layered_mode",
                    items=multi_layered_mode,
                    default=self.multi_layered_mode,
                    label="Multi-Layered EXR")
        ]

    def get_pre_create_attr_defs(self):
        attrs = super(CreateRedshiftROP, self).get_pre_create_attr_defs()

        return attrs + self.get_instance_attr_defs()
