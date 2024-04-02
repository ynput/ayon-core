import pyblish.api


class CollectFarmInstances(pyblish.api.InstancePlugin):
    """Collect instances for farm render."""

    order = pyblish.api.CollectorOrder
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    hosts = ["houdini"]
    targets = ["local", "remote"]
    label = "Collect farm instances"

    def process(self, instance):
        import hou

        creator_attribute = instance.data["creator_attributes"]
        product_type = instance.data["productType"]
        rop_node = hou.node(instance.data.get("instance_node"))

        # Align split parameter value on rop node to the render target.
        if creator_attribute.get("render_target") == "farm_split":
            if product_type == "arnold_rop":
                rop_node.setParms({"ar_ass_export_enable": 1})
            elif product_type == "mantra_rop":
                rop_node.setParms({"soho_outputmode": 1})
            elif product_type == "redshift_rop":
                rop_node.setParms({"RS_archive_enable": 1})
            elif product_type == "vray_rop":
                rop_node.setParms({"render_export_mode": "2"})
        else:
            if product_type == "arnold_rop":
                rop_node.setParms({"ar_ass_export_enable": 0})
            elif product_type == "mantra_rop":
                rop_node.setParms({"soho_outputmode": 0})
            elif product_type == "redshift_rop":
                rop_node.setParms({"RS_archive_enable": 0})
            elif product_type == "vray_rop":
                rop_node.setParms({"render_export_mode": "1"})

        # Collect Render Target
        if creator_attribute.get("render_target") not in {
            "farm_split", "farm"
        }:
            instance.data["farm"] = False
            self.log.debug("Render on farm is disabled. "
                           "Skipping farm collecting.")
            return

        instance.data["farm"] = True
        instance.data["families"].append("render.farm.hou")
