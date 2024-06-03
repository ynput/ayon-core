import os
import re

import hou
import pyblish.api

from ayon_core.hosts.houdini.api import colorspace
from ayon_core.hosts.houdini.api.lib import (
    evalParmNoFrame,
    get_color_management_preferences
)


class CollectUsdRender(pyblish.api.InstancePlugin):
    """Collect publishing data for USD Render ROP.

    If `rendercommand` parm is disabled (and thus no rendering triggers by the
    usd render rop) it is assumed to be a "Split Render" job where the farm
    will get an additional render job after the USD file is extracted.

    Provides:
        instance    -> ifdFile
        instance    -> colorspaceConfig
        instance    -> colorspaceDisplay
        instance    -> colorspaceView

    """

    label = "Collect USD Render Rop"
    order = pyblish.api.CollectorOrder
    hosts = ["houdini"]
    families = ["usdrender"]

    def process(self, instance):

        rop = hou.node(instance.data.get("instance_node"))

        # Store whether we are splitting the render job in an export + render
        split_render = not rop.parm("runcommand").eval()
        instance.data["splitRender"] = split_render
        if split_render:
            # USD file output
            lop_output = evalParmNoFrame(
                rop, "lopoutput", pad_character="#"
            )

            # The file is usually relative to the Output Processor's 'Save to
            # Directory' which forces all USD files to end up in that directory
            # TODO: It is possible for a user to disable this
            # TODO: When enabled I think only the basename of the `lopoutput`
            #  parm is preserved, any parent folders defined are likely ignored
            folder = evalParmNoFrame(
                rop, "savetodirectory_directory", pad_character="#"
            )

            export_file = os.path.join(folder, lop_output)

            # Substitute any # characters in the name back to their $F4
            # equivalent
            def replace_to_f(match):
                number = len(match.group(0))
                if number <= 1:
                    number = ""  # make it just $F not $F1 or $F0
                return "$F{}".format(number)

            export_file = re.sub("#+", replace_to_f, export_file)
            self.log.debug(
                "Found export file: {}".format(export_file)
            )
            instance.data["ifdFile"] = export_file

            # The render job is not frame dependent but fully dependent on
            # the job having been completed, since the extracted file is a
            # single file.
            if "$F" not in export_file:
                instance.data["splitRenderFrameDependent"] = False

        instance.data["farm"] = True  # always submit to farm

        # update the colorspace data
        colorspace_data = get_color_management_preferences()
        instance.data["colorspaceConfig"] = colorspace_data["config"]
        instance.data["colorspaceDisplay"] = colorspace_data["display"]
        instance.data["colorspaceView"] = colorspace_data["view"]

        # stub required data for Submit Publish Job publish plug-in
        instance.data["attachTo"] = []
        instance.data["renderProducts"] = colorspace.ARenderProduct()
