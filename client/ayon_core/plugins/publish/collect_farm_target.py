# -*- coding: utf-8 -*-
import pyblish.api


class CollectFarmTarget(pyblish.api.InstancePlugin):
    """Collects the render target for the instance
    """

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Farm Target"
    targets = ["local"]

    def process(self, instance):
        if not instance.data.get("farm"):
            return

        addons_manager = instance.context.data.get("ayonAddonsManager")

        farm_renderer_addons = ["deadline", "royalrender"]
        for farm_renderer in farm_renderer_addons:
            addon = addons_manager.get(farm_renderer)
            if addon and addon.enabled:
                farm_name = farm_renderer
                break
        else:
            # No enabled farm render addon found, then report all farm
            # addons that were searched for yet not found
            for farm_renderer in farm_renderer_addons:
                self.log.error(f"Cannot find AYON addon '{farm_renderer}'.")
            raise RuntimeError("No AYON renderer addon found.")

        self.log.debug("Collected render target: {0}".format(farm_name))
        instance.data["toBeRenderedOn"] = farm_name
