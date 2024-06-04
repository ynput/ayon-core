import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.lib import get_version_from_path


class CollectWorkfileVersion(pyblish.api.ContextPlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Current Workfile Version"
    hosts = ["substancepainter"]

    def process(self, context):
        host = registered_host()
        path = host.get_current_workfile()
        version = int(get_version_from_path(path))
        context.data["version"] = version
        self.log.debug(f"Current Version: {version}")