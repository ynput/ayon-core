import os
from datetime import datetime
import shutil

import pyblish.api

from ayon_core.pipeline import registered_host


class ExtractRenderOnFarm(pyblish.api.InstancePlugin):
    """Copy the workfile to a timestamped copy."""

    order = pyblish.api.ExtractorOrder + 0.499
    label = "Extract Render On Farm"
    hosts = ["nuke"]
    families = ["render_on_farm"]

    settings_category = "nuke"

    def process(self, instance):
        if not instance.context.data.get("render_on_farm", False):
            return

        host = registered_host()
        current_datetime = datetime.now()
        formatted_timestamp = current_datetime.strftime("%Y%m%d%H%M%S")
        base, ext = os.path.splitext(host.current_file())

        directory = os.path.join(os.path.dirname(base), "farm_submissions")
        if not os.path.exists(directory):
            os.makedirs(directory)

        filename = "{}_{}{}".format(
            os.path.basename(base), formatted_timestamp, ext
        )
        path = os.path.join(directory, filename).replace("\\", "/")
        instance.context.data["currentFile"] = path
        shutil.copy(host.current_file(), path)
