import pyblish.api


class CollectNoProductTypeFamilyDynamic(pyblish.api.InstancePlugin):
    """Collect data for caching to Deadline."""

    order = pyblish.api.CollectorOrder - 0.49
    families = ["dynamic"]
    hosts = ["houdini"]
    targets = ["local", "remote"]
    label = "Override Dynamic Instance families"

    def process(self, instance):
        # Do not allow `productType` to creep into the pyblish families
        # so that e.g. any regular plug-ins for `pointcache` or alike do
        # not trigger.
        instance.data["family"] = "dynamic"
        instance.data["families"] = ["dynamic"]
