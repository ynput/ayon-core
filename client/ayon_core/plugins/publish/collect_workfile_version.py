import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.lib import get_version_from_path


class CollectWorkfileVersion(pyblish.api.ContextPlugin):
    """Collect current workfile version as context data"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Current Workfile Version"

    def process(self, context):
        host = registered_host()
        path = host.get_current_workfile()
        if path:
            version = int(get_version_from_path(path))
            context.data["version"] = version
            self.log.debug(f"Current Version: {version}")
