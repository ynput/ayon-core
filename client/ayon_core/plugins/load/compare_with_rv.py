import json
import qargparse
from qtpy import QtCore, QtWidgets, QtGui


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

    options = [
        qargparse.Choice(
            "version_to_compare",
            label="Select version to compare to",
            items=["1", "2", "3", "4"],
            default="1",
            help="Which version to you want to compare to?"
        ),
        qargparse.Boolean(
            "shall_load_plate",
            label="Load Plate",
            default=False,
            help="Loads the main plate aswell"
        ),
    ]

    def load(self, context, name, namespace, data):
        self.log.warning(f"{self.rvcon.connected = }")
