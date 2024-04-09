from ayon_core.hosts.houdini.api import plugin
from ayon_core.lib import EnumDef


class CreateArnoldRop(plugin.HoudiniCreator):
    """Arnold ROP"""

    identifier = "io.openpype.creators.houdini.arnold_rop"
    label = "Arnold ROP"
    product_type = "arnold_rop"
    icon = "magic"

    # Default extension
    ext = "exr"

    # Default render target
    render_target = "farm_split"

    def create(self, product_name, instance_data, pre_create_data):
        import hou
        # Transfer settings from pre create to instance
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        creator_attributes.update(pre_create_data)

        # Remove the active, we are checking the bypass flag of the nodes
        instance_data.pop("active", None)
        instance_data.update({"node_type": "arnold"})

        # Add chunk size attribute
        instance_data["chunkSize"] = 1

        instance = super(CreateArnoldRop, self).create(
            product_name,
            instance_data,
            pre_create_data)  # type: plugin.CreatedInstance

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

        if pre_create_data.get("render_target") == "farm_split":
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

    def get_instance_attr_defs(self):
        image_format_enum = [
            "bmp", "cin", "exr", "jpg", "pic", "pic.gz", "png",
            "rad", "rat", "rta", "sgi", "tga", "tif",
        ]
        render_target_items = {
            "local": "Local machine rendering",
            "local_no_render": "Use existing frames (local)",
            "farm": "Farm Rendering",
            "farm_split": "Farm Rendering - Split export & render jobs",
        }

        return [
            EnumDef("render_target",
                    items=render_target_items,
                    label="Render target",
                    default=self.render_target),
            EnumDef("image_format",
                    image_format_enum,
                    default=self.ext,
                    label="Image Format Options"),
        ]

    def get_pre_create_attr_defs(self):
        attrs = super(CreateArnoldRop, self).get_pre_create_attr_defs()

        return attrs + self.get_instance_attr_defs()
