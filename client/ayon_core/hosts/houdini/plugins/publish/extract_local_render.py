import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.hosts.houdini.api.lib import render_rop
import hou


class ExtractLocalRender(publish.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Local Render"
    hosts = ["houdini"]
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]
    targets = ["local", "remote"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        creator_attribute = instance.data["creator_attributes"]

        if creator_attribute.get("render_target") == "local_no_render":
            self.log.debug("Skip render is enabled, skipping rendering.")
            return

        # Make sure split parameter is turned off.
        # Otherwise, render nodes will generate intermediate
        #  render files instead of render.
        product_type = instance.data["productType"]
        rop_node = hou.node(instance.data.get("instance_node"))

        if product_type == "arnold_rop":
            rop_node.setParms({"ar_ass_export_enable": 0})
        elif product_type == "mantra_rop":
            rop_node.setParms({"soho_outputmode": 0})
        elif product_type == "redshift_rop":
            rop_node.setParms({"RS_archive_enable": 0})
        elif product_type == "vray_rop":
            rop_node.setParms({"render_export_mode": "1"})

        ropnode = hou.node(instance.data.get("instance_node"))
        render_rop(ropnode)

        # TODO: Check for missing frames.
        # self.log.debug(instance.data["expectedFiles"])
