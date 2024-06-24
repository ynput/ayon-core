import pyblish.api


class CollectNoProductTypeFamilyGeneric(pyblish.api.InstancePlugin):
    """Collect data for caching to Deadline."""

    order = pyblish.api.CollectorOrder - 0.49
    families = ["generic"]
    hosts = ["houdini"]
    targets = ["local", "remote"]
    label = "Collect Data for Cache"

    def process(self, instance):
        # Do not allow `productType` to creep into the pyblish families
        # so that e.g. any regular plug-ins for `pointcache` or alike do
        # not trigger.
        instance.data["family"] = "generic"
        # TODO: Do not add the dynamic 'rop' family in the collector?
        instance.data["families"] = ["generic", "rop"]