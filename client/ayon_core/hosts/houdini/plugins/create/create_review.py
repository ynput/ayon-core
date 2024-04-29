# -*- coding: utf-8 -*-
"""Creator plugin for creating openGL reviews."""
from ayon_core.hosts.houdini.api import lib, plugin
from ayon_core.lib import EnumDef, BoolDef, NumberDef

import os
import hou


class CreateReview(plugin.HoudiniCreator):
    """Review with OpenGL ROP"""

    identifier = "io.openpype.creators.houdini.review"
    label = "Review"
    product_type = "review"
    icon = "video-camera"
    review_color_space = ""

    def apply_settings(self, project_settings):
        super(CreateReview, self).apply_settings(project_settings)
        # workfile settings added in '0.2.13'
        color_settings = project_settings["houdini"]["imageio"].get(
            "workfile", {}
        )
        if color_settings.get("enabled"):
            self.review_color_space = color_settings.get("review_color_space")

    def create(self, product_name, instance_data, pre_create_data):

        instance_data.pop("active", None)
        instance_data.update({"node_type": "opengl"})
        instance_data["imageFormat"] = pre_create_data.get("imageFormat")
        instance_data["keepImages"] = pre_create_data.get("keepImages")

        instance = super(CreateReview, self).create(
            product_name,
            instance_data,
            pre_create_data)

        instance_node = hou.node(instance.get("instance_node"))

        frame_range = hou.playbar.frameRange()

        filepath = "{root}/{product_name}/{product_name}.$F4.{ext}".format(
            root=hou.text.expandString("$HIP/pyblish"),
            # keep dynamic link to product name
            product_name="`chs(\"AYON_productName\")`",
            ext=pre_create_data.get("image_format") or "png"
        )

        parms = {
            "picture": filepath,

            "trange": 1,

            # Unlike many other ROP nodes the opengl node does not default
            # to expression of $FSTART and $FEND so we preserve that behavior
            # but do set the range to the frame range of the playbar
            "f1": frame_range[0],
            "f2": frame_range[1],
        }

        override_resolution = pre_create_data.get("override_resolution")
        if override_resolution:
            parms.update({
                "tres": override_resolution,
                "res1": pre_create_data.get("resx"),
                "res2": pre_create_data.get("resy"),
                "aspect": pre_create_data.get("aspect"),
            })

        if self.selected_nodes:
            # The first camera found in selection we will use as camera
            # Other node types we set in force objects
            camera = None
            force_objects = []
            for node in self.selected_nodes:
                path = node.path()
                if node.type().name() == "cam":
                    if camera:
                        continue
                    camera = path
                else:
                    force_objects.append(path)

            if not camera:
                self.log.warning("No camera found in selection.")

            parms.update({
                "camera": camera or "",
                "scenepath": "/obj",
                "forceobjects": " ".join(force_objects),
                "vobjects": ""  # clear candidate objects from '*' value
            })

        instance_node.setParms(parms)

        # Set OCIO Colorspace to the default colorspace
        #  if there's OCIO
        if os.getenv("OCIO"):
            # Fall to the default value if cls.review_color_space is empty.
            if not self.review_color_space:
                # cls.review_color_space is an empty string
                #  when the imageio/workfile setting is disabled or
                #  when the Review colorspace setting is empty.
                from ayon_core.hosts.houdini.api.colorspace import get_default_display_view_colorspace  # noqa
                self.review_color_space = get_default_display_view_colorspace()

            lib.set_review_color_space(instance_node,
                                       self.review_color_space,
                                       self.log)

        to_lock = ["id", "productType"]

        self.lock_parameters(instance_node, to_lock)

    def get_pre_create_attr_defs(self):
        attrs = super(CreateReview, self).get_pre_create_attr_defs()

        image_format_enum = [
            "bmp", "cin", "exr", "jpg", "pic", "pic.gz", "png",
            "rad", "rat", "rta", "sgi", "tga", "tif",
        ]

        return attrs + [
            BoolDef("keepImages",
                    label="Keep Image Sequences",
                    default=False),
            EnumDef("imageFormat",
                    image_format_enum,
                    default="png",
                    label="Image Format Options"),
            BoolDef("override_resolution",
                    label="Override resolution",
                    tooltip="When disabled the resolution set on the camera "
                            "is used instead.",
                    default=True),
            NumberDef("resx",
                      label="Resolution Width",
                      default=1280,
                      minimum=2,
                      decimals=0),
            NumberDef("resy",
                      label="Resolution Height",
                      default=720,
                      minimum=2,
                      decimals=0),
            NumberDef("aspect",
                      label="Aspect Ratio",
                      default=1.0,
                      minimum=0.0001,
                      decimals=3)
        ]
