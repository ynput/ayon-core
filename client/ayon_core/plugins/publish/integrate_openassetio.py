import pyblish.api
import openassetio


class IntegrateOpenAssetIO(pyblish.api.InstancePlugin):
    label = "Integrate OpenAssetIO"
    order = pyblish.api.IntegratorOrder
    families = ["traits"]

    def process(self, instance):
        try:
            # type: openassetio.managerApi.Manager
            manager = instance.context.data["openAssetIOManager"]
        except KeyError:
            self.log.warning(
                "OpenAssetIOManager not found in context. Skipping.")
            return

        # process old-fashioned representations to
        # traits defined models
        # TODO: add support of new style representations

        if not instance.data["representations"]:
            self.log.info("No representations found. Skipping.")
            return

        traits_data = instance.data["traits_data"]

        for representation in instance.data["representations"]:
            self.log.debug(
                f"Processing representation: {representation['name']}")

