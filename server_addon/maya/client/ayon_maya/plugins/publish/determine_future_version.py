import pyblish.api
from ayon_maya.api import plugin


class DetermineFutureVersion(plugin.MayaInstancePlugin):
    """
    This will determine version of product if we want render to be attached to.
    """
    label = "Determine Product Version"
    order = pyblish.api.IntegratorOrder
    families = ["renderlayer"]

    def process(self, instance):
        context = instance.context
        attatch_to_products = [
            i["productName"]
            for i in instance.data["attachTo"]
        ]
        if not attatch_to_products:
            return

        for i in context:
            if i.data["productName"] not in attatch_to_products:
                continue
            # # this will get corresponding product in attachTo list
            # # so we can set version there
            sub = next(
                item
                for item in instance.data["attachTo"]
                if item["productName"] == i.data["productName"]
            )

            sub["version"] = i.data.get("version", 1)
            self.log.info("render will be attached to {} v{}".format(
                    sub["productName"], sub["version"]
            ))
