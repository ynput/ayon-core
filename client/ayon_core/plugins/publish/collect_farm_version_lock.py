import pyblish.api


class CollectFarmVersionLock(pyblish.api.ContextPlugin):
    """Define whether 'version' metadata should be written along with the
    submission.

    Collect whether the version should be locked in the farm metadata JSON.

    Note: this locking will only occur if enabled AND the instance data has a
        version collected, so e.g. "Collect Scene Version" may need to still
        be enabled and run for the host for the locking to occur.
    """
    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Farm Version Lock"
    settings_category = "core"
    targets = ["local"]

    lock_version_on_farm = True

    def process(self, context):
        context.data["lockVersionOnFarm"] = self.lock_version_on_farm
        self.log.debug(f"Lock version on farm: {self.lock_version_on_farm}")