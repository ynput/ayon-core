# -*- coding: utf-8 -*-
"""Creator plugin to create Karma ROP."""
from ayon_houdini.api import plugin
from ayon_core.lib import BoolDef, EnumDef, NumberDef


class CreateKarmaROP(plugin.HoudiniCreator):
    """Karma ROP"""
    identifier = "io.openpype.creators.houdini.karma_rop"
    label = "Karma ROP"
    product_type = "karma_rop"
    icon = "magic"

    # Default render target
    render_target = "farm"

    def create(self, product_name, instance_data, pre_create_data):
        import hou  # noqa
        # Transfer settings from pre create to instance
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())

        for key in ["render_target", "review"]:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]

        instance_data.pop("active", None)
        instance_data.update({"node_type": "karma"})
        # Add chunk size attribute
        instance_data["chunkSize"] = 10

        instance = super(CreateKarmaROP, self).create(
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
        checkpoint = "{cp_dir}{product_name}.$F4.checkpoint".format(
            cp_dir=hou.text.expandString("$HIP/pyblish/"),
            product_name=product_name
        )

        usd_directory = "{usd_dir}{product_name}_$RENDERID".format(
            usd_dir=hou.text.expandString("$HIP/pyblish/renders/usd_renders/"),     # noqa
            product_name=product_name
        )

        parms = {
            # Render Frame Range
            "trange": 1,
            # Karma ROP Setting
            "picture": filepath,
            # Karma Checkpoint Setting
            "productName": checkpoint,
            # USD Output Directory
            "savetodirectory": usd_directory,
        }

        res_x = pre_create_data.get("res_x")
        res_y = pre_create_data.get("res_y")

        if self.selected_nodes:
            # If camera found in selection
            # we will use as render camera
            camera = None
            for node in self.selected_nodes:
                if node.type().name() == "cam":
                    camera = node.path()
                    has_camera = pre_create_data.get("cam_res")
                    if has_camera:
                        res_x = node.evalParm("resx")
                        res_y = node.evalParm("resy")

            if not camera:
                self.log.warning("No render camera found in selection")

            parms.update({
                "camera": camera or "",
                "resolutionx": res_x,
                "resolutiony": res_y,
            })

        instance_node.setParms(parms)

        # Lock some Avalon attributes
        to_lock = ["productType", "id"]
        self.lock_parameters(instance_node, to_lock)

    def get_instance_attr_defs(self):
        """get instance attribute definitions.

        Attributes defined in this method are exposed in
            publish tab in the publisher UI.
        """

        render_target_items = {
            "local": "Local machine rendering",
            "local_no_render": "Use existing frames (local)",
            "farm": "Farm Rendering",
        }

        return [
            BoolDef("review",
                    label="Review",
                    tooltip="Mark as reviewable",
                    default=True),
            EnumDef("render_target",
                    items=render_target_items,
                    label="Render target",
                    default=self.render_target)
        ]


    def get_pre_create_attr_defs(self):
        image_format_enum = [
            "bmp", "cin", "exr", "jpg", "pic", "pic.gz", "png",
            "rad", "rat", "rta", "sgi", "tga", "tif",
        ]

        attrs = super(CreateKarmaROP, self).get_pre_create_attr_defs()

        attrs += [
            EnumDef("image_format",
                    image_format_enum,
                    default="exr",
                    label="Image Format Options"),
            NumberDef("res_x",
                      label="width",
                      default=1920,
                      decimals=0),
            NumberDef("res_y",
                      label="height",
                      default=720,
                      decimals=0),
            BoolDef("cam_res",
                    label="Camera Resolution",
                    default=False),
        ]
        return attrs + self.get_instance_attr_defs()
