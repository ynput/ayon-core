"""A module containing generic loader actions that will display in the Loader.

"""

from ayon_houdini.api import plugin


class SetFrameRangeLoader(plugin.HoudiniLoader):
    """Set frame range excluding pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "pointcache",
        "vdbcache",
        "usd",
    }
    representations = {"abc", "vdb", "usd"}

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        import hou

        version_attributes = context["version"]["attrib"]

        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        if start is None or end is None:
            print(
                "Skipping setting frame range because start or "
                "end frame data is missing.."
            )
            return

        hou.playbar.setFrameRange(start, end)
        hou.playbar.setPlaybackRange(start, end)


class SetFrameRangeWithHandlesLoader(plugin.HoudiniLoader):
    """Set frame range including pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "pointcache",
        "vdbcache",
        "usd",
    }
    representations = {"abc", "vdb", "usd"}

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        import hou

        version_attributes = context["version"]["attrib"]

        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        if start is None or end is None:
            print(
                "Skipping setting frame range because start or "
                "end frame data is missing.."
            )
            return

        # Include handles
        start -= version_attributes.get("handleStart", 0)
        end += version_attributes.get("handleEnd", 0)

        hou.playbar.setFrameRange(start, end)
        hou.playbar.setPlaybackRange(start, end)
