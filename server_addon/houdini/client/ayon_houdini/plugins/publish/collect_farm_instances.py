import pyblish.api
from ayon_houdini.api import plugin


class CollectFarmInstances(plugin.HoudiniInstancePlugin):
    """Collect instances for farm render."""

    order = pyblish.api.CollectorOrder
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    targets = ["local", "remote"]
    label = "Collect farm instances"

    def process(self, instance):

        creator_attribute = instance.data["creator_attributes"]

        # Collect Render Target
        if creator_attribute.get("render_target") not in {
            "farm_split", "farm"
        }:
            instance.data["farm"] = False
            instance.data["splitRender"] = False
            self.log.debug("Render on farm is disabled. "
                           "Skipping farm collecting.")
            return

        instance.data["farm"] = True
        instance.data["splitRender"] = (
            creator_attribute.get("render_target") == "farm_split"
        )
