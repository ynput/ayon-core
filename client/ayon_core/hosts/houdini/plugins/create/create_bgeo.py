# -*- coding: utf-8 -*-
"""Creator plugin for creating pointcache bgeo files."""
from ayon_core.hosts.houdini.api import lib, plugin
from ayon_core.pipeline import CreatorError
import hou
from ayon_core.lib import EnumDef, BoolDef


class CreateBGEO(plugin.HoudiniCreator):
    """BGEO pointcache creator."""
    identifier = "io.openpype.creators.houdini.bgeo"
    label = "PointCache (Bgeo)"
    product_type = "pointcache"
    icon = "gears"

    def create(self, product_name, instance_data, pre_create_data):

        instance_data.pop("active", None)

        instance_data.update({"node_type": "geometry"})
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        creator_attributes["farm"] = pre_create_data["farm"]
        # Transfer settings from pre create to instance
        data_to_transfer = ["farm", "bgeo_type"]
        for key in data_to_transfer:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]

        instance = super(CreateBGEO, self).create(
            product_name,
            instance_data,
            pre_create_data)

        instance_node = hou.node(instance.get("instance_node"))

        file_path = "{export_dir}/{product_name}.$F4.{ext}".format(
            export_dir=hou.text.expandString("$HIP/pyblish"),
            product_name=product_name,
            ext=pre_create_data.get("bgeo_type") or "bgeo.sc"
        )
        parms = {
            "sopoutput": file_path
        }

        instance_node.parm("trange").set(1)
        if self.selected_nodes:
            # if selection is on SOP level, use it
            if isinstance(self.selected_nodes[0], hou.SopNode):
                parms["soppath"] = self.selected_nodes[0].path()
            else:
                # try to find output node with the lowest index
                outputs = [
                    child for child in self.selected_nodes[0].children()
                    if child.type().name() == "output"
                ]
                if not outputs:
                    instance_node.setParms(parms)
                    raise CreatorError((
                        "Missing output node in SOP level for the selection. "
                        "Please select correct SOP path in created instance."
                    ))
                outputs.sort(key=lambda output: output.evalParm("outputidx"))
                parms["soppath"] = outputs[0].path()

        instance_node.setParms(parms)

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

        file_path, _ = lib.splitext(
            node.evalParm("sopoutput"),
            allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"
            ]
        )

        output = "{file_path}.{ext}".format(
            file_path=file_path,
            ext=creator_attributes["bgeo_type"]
        )

        node.setParms({"sopoutput": output})

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
        _, ext = lib.splitext(
            node.parm("sopoutput").unexpandedString(),
            allowed_multidot_extensions=[
                ".ass.gz", ".bgeo.sc", ".bgeo.gz",
                ".bgeo.lzma", ".bgeo.bz2"
            ]
        )
        node_data = {
            "creator_attributes": {
                "bgeo_type": ext[1:]  # Remove the leading .
            }
        }

        return node_data

    def get_instance_attr_defs(self):
        bgeo_enum = {
            "bgeo": "uncompressed bgeo (.bgeo)",
            "bgeosc": "BLOSC compressed bgeo (.bgeosc)",
            "bgeo.sc": "BLOSC compressed bgeo (.bgeo.sc)",
            "bgeo.gz": "GZ compressed bgeo (.bgeo.gz)",
            "bgeo.lzma": "LZMA compressed bgeo (.bgeo.lzma)",
            "bgeo.bz2": "BZip2 compressed bgeo (.bgeo.bz2)",
        }

        return [
            BoolDef("farm",
                    label="Submitting to Farm",
                    default=False),
            EnumDef("bgeo_type",
                    items=bgeo_enum,
                    default="bgeo",
                    label="BGEO Options")
        ]

    def get_pre_create_attr_defs(self):
        attrs = super().get_pre_create_attr_defs()

        return attrs + self.get_instance_attr_defs()

    def get_network_categories(self):
        return [
            hou.ropNodeTypeCategory(),
            hou.sopNodeTypeCategory()
        ]
