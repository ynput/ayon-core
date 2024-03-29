import pyblish.api


class CollectFarmInstances(pyblish.api.InstancePlugin):
    """Collect instances for farm render."""

    order = pyblish.api.CollectorOrder
    families = ["mantra_rop",
                "karma_rop"]

    hosts = ["houdini"]
    targets = ["local", "remote"]
    label = "Collect farm instances"

    def process(self, instance):
        creator_attribute = instance.data["creator_attributes"]
        farm_enabled = creator_attribute["farm"]
        instance.data["farm"] = farm_enabled
        if not farm_enabled:
            self.log.debug("Render on farm is disabled. "
                           "Skipping farm collecting.")
            return

        instance.data["families"].append("render.farm.hou")
