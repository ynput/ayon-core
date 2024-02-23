
import pyblish.api


class CollectCurrentFile(pyblish.api.InstancePlugin):
    label = "Collect CurrentFile"
    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["zbrush"]
    families = ["workfile"]

    def process(self, instance):
        context = instance.context