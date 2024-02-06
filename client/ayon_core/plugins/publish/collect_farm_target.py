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

        context = instance.context

        farm_name = ""
        addons_manager = context.data.get("ayonAddonsManger")

        for farm_renderer in ["deadline", "royalrender"]:
            addon = addons_manager.get(farm_renderer, False)

            if not addon:
                self.log.error("Cannot find AYON addon '{0}'.".format(
                    farm_renderer))
            elif addon.enabled:
                farm_name = farm_renderer

        if farm_name:
            self.log.debug("Collected render target: {0}".format(farm_name))
            instance.data["toBeRenderedOn"] = farm_name
        else:
            AssertionError("No OpenPype renderer module found")
