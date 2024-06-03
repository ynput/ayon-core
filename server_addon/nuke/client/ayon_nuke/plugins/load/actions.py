"""A module containing generic loader actions that will display in the Loader.

"""

from ayon_core.lib import Logger
from ayon_core.pipeline import load
from ayon_nuke.api import lib

log = Logger.get_logger(__name__)


class SetFrameRangeLoader(load.LoaderPlugin):
    """Set frame range excluding pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "write",
        "yeticache",
        "pointcache",
    }
    representations = {"*"}
    extensions = {"*"}

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):
        version_entity = context["version"]
        version_attributes = version_entity["attrib"]

        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        log.info("start: {}, end: {}".format(start, end))
        if start is None or end is None:
            log.info("Skipping setting frame range because start or "
                     "end frame data is missing..")
            return

        lib.update_frame_range(start, end)


class SetFrameRangeWithHandlesLoader(load.LoaderPlugin):
    """Set frame range including pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "write",
        "yeticache",
        "pointcache",
    }
    representations = {"*"}

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):
        version_attributes = context["version"]["attrib"]
        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        # Include handles
        start -= version_attributes.get("handleStart", 0)
        end += version_attributes.get("handleEnd", 0)

        lib.update_frame_range(start, end)
