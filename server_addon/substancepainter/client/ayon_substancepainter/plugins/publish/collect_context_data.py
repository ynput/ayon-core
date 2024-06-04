import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.lib import get_version_from_path


class CollectContextData(pyblish.api.ContextPlugin):
    """Collect current context publish"""

    order = pyblish.api.CollectorOrder - 0.49
    label = "Collect Context Data"
    hosts = ["substancepainter"]

    def process(self, context):
        host = registered_host()
        path = host.get_current_workfile()
        context.data["currentFile"] = path
        self.log.debug(f"Current workfile: {path}")
        version = int(get_version_from_path(path))
        context.data["version"] = version
        self.log.debug(f"Current Version: {version}")
