from ayon_core.hosts.houdini.api import lib, plugin
from ayon_core.lib import EnumDef, BoolDef


class CreateArnoldRop(plugin.HoudiniCreator):
    """Arnold ROP"""

    identifier = "io.openpype.creators.houdini.arnold_rop"
    label = "Arnold ROP"
    product_type = "arnold_rop"
    icon = "magic"

    # Default extension
    ext = "exr"

    # Default to split export and render jobs
    export_job = True

    def create(self, product_name, instance_data, pre_create_data):
        import hou

        # Remove the active, we are checking the bypass flag of the nodes
        instance_data.pop("active", None)
        instance_data.update({"node_type": "arnold"})

        # Add chunk size attribute
        instance_data["chunkSize"] = 1
        # Submit for job publishing
        instance_data["farm"] = pre_create_data.get("farm")

        instance = super(CreateArnoldRop, self).create(
            product_name,
            instance_data,
            pre_create_data)

        instance_node = hou.node(instance.get("instance_node"))

        ext = pre_create_data.get("image_format")

        filepath = "{renders_dir}{product_name}/{product_name}.$F4.{ext}".format(
            renders_dir=hou.text.expandString("$HIP/pyblish/renders/"),
            product_name=product_name,
            ext=ext,
        )
        parms = {
            # Render frame range
            "trange": 1,

            # Arnold ROP settings
            "ar_picture": filepath,
            "ar_exr_half_precision": 1           # half precision
        }

        if pre_create_data.get("export_job"):
            ass_filepath = \
                "{export_dir}{product_name}/{product_name}.$F4.ass".format(
                    export_dir=hou.text.expandString("$HIP/pyblish/ass/"),
                    product_name=product_name,
                )
            parms["ar_ass_export_enable"] = 1
            parms["ar_ass_file"] = ass_filepath

        instance_node.setParms(parms)

        # Lock any parameters in this list
        to_lock = ["productType", "id"]
        self.lock_parameters(instance_node, to_lock)

    @staticmethod
    def update_node_parameters(node, creator_attributes):
        """update node parameters according to creator attributes.

        Implementation of update_node_parameters.

        Args:
            node(hou.Node): Houdini node to apply changes to.
            creator_attributes(dict): Dictionary of creator attributes.
        """
        file_path, _ = lib.splitext(
            node.evalParm("ar_picture"),
            allowed_multidot_extensions=["pic.gz"]
        )
        output = "{file_path}.{ext}".format(
            file_path=file_path,
            ext=creator_attributes["image_format"]
        )

        node.setParms({
            "ar_picture": output,
            "ar_ass_export_enable": creator_attributes.get("export_job")
        })

    def get_instance_attr_defs(self):
        image_format_enum = [
            "bmp", "cin", "exr", "jpg", "pic", "pic.gz", "png",
            "rad", "rat", "rta", "sgi", "tga", "tif",
        ]

        return [
            BoolDef("farm",
                    label="Submitting to Farm",
                    default=True),
            BoolDef("export_job",
                    label="Split export and render jobs",
                    default=self.export_job),
            EnumDef("image_format",
                    image_format_enum,
                    default=self.ext,
                    label="Image Format Options")
        ]

    def get_pre_create_attr_defs(self):
        attrs = super(CreateArnoldRop, self).get_pre_create_attr_defs()

        return attrs + self.get_instance_attr_defs()
