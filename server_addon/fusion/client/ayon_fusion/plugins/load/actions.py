"""A module containing generic loader actions that will display in the Loader.

"""

from ayon_core.pipeline import load


class FusionSetFrameRangeLoader(load.LoaderPlugin):
    """Set frame range excluding pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "imagesequence",
        "render",
        "yeticache",
        "pointcache",
        "render",
    }
    representations = {"*"}
    extensions = {"*"}

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        from ayon_fusion.api import lib

        version_attributes = context["version"]["attrib"]

        start = version_attributes.get("frameStart", None)
        end = version_attributes.get("frameEnd", None)

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        lib.update_frame_range(start, end)


class FusionSetFrameRangeWithHandlesLoader(load.LoaderPlugin):
    """Set frame range including pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "imagesequence",
        "render",
        "yeticache",
        "pointcache",
        "render",
    }
    representations = {"*"}

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        from ayon_fusion.api import lib

        version_attributes = context["version"]["attrib"]
        start = version_attributes.get("frameStart", None)
        end = version_attributes.get("frameEnd", None)

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        # Include handles
        start -= version_attributes.get("handleStart", 0)
        end += version_attributes.get("handleEnd", 0)

        lib.update_frame_range(start, end)
