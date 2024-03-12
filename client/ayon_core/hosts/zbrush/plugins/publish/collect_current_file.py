
import pyblish.api
from ayon_core.pipeline import registered_host


class CollectCurrentFile(pyblish.api.ContextPlugin):
    label = "Collect Current File"
    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["zbrush"]

    def process(self, context):
        host = registered_host()
        current_file = host.get_current_workfile()
        if not current_file:
            self.log.error("Scene is not saved. Please save the "
                           "scene with AYON workfile tools.")
        context.data["currentFile"] = current_file
