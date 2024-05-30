import os
import pyblish.api

from pymxs import runtime as rt


class CollectCurrentFile(pyblish.api.ContextPlugin):
    """Inject the current working file."""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Max Current File"
    hosts = ['max']

    def process(self, context):
        """Inject the current working file"""
        folder = rt.maxFilePath
        file = rt.maxFileName
        if not folder or not file:
            self.log.error("Scene is not saved.")
        current_file = os.path.join(folder, file)

        context.data["currentFile"] = current_file
        self.log.debug("Scene path: {}".format(current_file))
