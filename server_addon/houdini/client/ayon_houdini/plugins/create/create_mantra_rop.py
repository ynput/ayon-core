# -*- coding: utf-8 -*-
"""Creator plugin to create Mantra ROP."""
from ayon_houdini.api import plugin
from ayon_core.lib import EnumDef, BoolDef


class CreateMantraROP(plugin.HoudiniCreator):
    """Mantra ROP"""
    identifier = "io.openpype.creators.houdini.mantra_rop"
    label = "Mantra ROP"
    product_type = "mantra_rop"
    icon = "magic"

    # Default render target
    render_target = "farm_split"

    def create(self, product_name, instance_data, pre_create_data):
        import hou  # noqa
        # Transfer settings from pre create to instance
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        for key in ["render_target", "review"]:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]

        instance_data.pop("active", None)
        instance_data.update({"node_type": "ifd"})
        # Add chunk size attribute
        instance_data["chunkSize"] = 10

        instance = super(CreateMantraROP, self).create(
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
            # Render Frame Range
            "trange": 1,
            # Mantra ROP Setting
            "vm_picture": filepath,
        }

        if pre_create_data.get("render_target") == "farm_split":
            ifd_filepath = \
                "{export_dir}{product_name}/{product_name}.$F4.ifd".format(
                    export_dir=hou.text.expandString("$HIP/pyblish/ifd/"),
                    product_name=product_name,
                )
            parms["soho_outputmode"] = 1
            parms["soho_diskfile"] = ifd_filepath

        if self.selected_nodes:
            # If camera found in selection
            # we will use as render camera
            camera = None
            for node in self.selected_nodes:
                if node.type().name() == "cam":
                    camera = node.path()

            if not camera:
                self.log.warning("No render camera found in selection")

            parms.update({"camera": camera or ""})

        custom_res = pre_create_data.get("override_resolution")
        if custom_res:
            parms.update({"override_camerares": 1})
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
            "farm_split": "Farm Rendering - Split export & render jobs",
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

        attrs = super(CreateMantraROP, self).get_pre_create_attr_defs()

        attrs += [
            EnumDef("image_format",
                    image_format_enum,
                    default="exr",
                    label="Image Format Options"),
            BoolDef("override_resolution",
                    label="Override Camera Resolution",
                    tooltip="Override the current camera "
                            "resolution, recommended for IPR.",
                    default=False),
        ]
        return attrs + self.get_instance_attr_defs()
