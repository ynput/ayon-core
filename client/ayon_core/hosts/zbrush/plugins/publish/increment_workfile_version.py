import pyblish.api
from ayon_core.lib import version_up
from ayon_core.pipeline import registered_host


class IncrementWorkfileVersion(pyblish.api.ContextPlugin):
    """Save current file"""

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    hosts = ["zbrush"]
    families = ["workfile"]

    def process(self, context):
        host = registered_host()
        path = context.data["currentFile"]
        self.log.info(f"Increment and save workfile: {path}")
        host.save_workfile(version_up(path))
