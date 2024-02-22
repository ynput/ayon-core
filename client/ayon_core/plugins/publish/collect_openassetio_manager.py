from ayon_core.pipeline import get_openassetio_manager
import pyblish.api


class CollectOpenAssetIOManager(publish.api.Context):
    label = "Collect OpenAssetIO Manager"
    order = pyblish.api.CollectorOrder

    def process(self, context):
        manager = get_openassetio_manager()
        context.data["openassetio_manager"] = manager
