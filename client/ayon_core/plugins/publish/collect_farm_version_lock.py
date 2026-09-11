import pyblish.api


class CollectFarmVersionLock(pyblish.api.ContextPlugin):
    """Define whether 'version' metadata should be written along with the
    submission.

    Collect whether the version should be locked in the farm metadata JSON.

    Note: this locking will only occur if enabled AND a ``version`` is
        present on the instances used for farm submission (e.g. set on
        ``instance.data["version"]`` by collectors such as
        ``CollectAnatomyInstanceData`` or "Collect Scene Version").
    """
    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Farm Version Lock"
    settings_category = "core"
    targets = ["local"]

    lock_version_on_farm = True

    def process(self, context):
        context.data["lockVersionOnFarm"] = self.lock_version_on_farm
        self.log.debug(f"Lock version on farm: {self.lock_version_on_farm}")