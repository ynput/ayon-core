import json
from ayon_core.lib import ApplicationManager
from ayon_core.pipeline import load, get_current_context

# from ayon_openrv.api import RvCommunicator


class CompareWithRV(load.LoaderPlugin):
    """Open Image Sequence with system default"""

    families = ["render", "review", "plate"]
    representations = ["*"]
    extensions = ["*"]

    label = "Compare with RV"
    order = -10
    icon = "play-circle"
    color = "orange"
    # rvcon = RvCommunicator("ayon")

    def load(self, context, name, namespace, data):
        self.log.warning(f"{self.rvcon.connected = }")
