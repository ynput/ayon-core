
import pyblish.api
from ayon_core.pipeline import registered_host


class CollectCurrentFile(pyblish.api.InstancePlugin):
    label = "Collect CurrentFile"
    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["zbrush"]
    families = ["workfile"]

    def process(self, instance):
        host = registered_host()
        context = instance.context
        currentFile = host.get_current_workfile()
        if not currentFile:
            self.log.error("Scene is not saved. Please save the "
                           "scene with AYON workfile tools.")
        context.data["currentFile"] = currentFile
