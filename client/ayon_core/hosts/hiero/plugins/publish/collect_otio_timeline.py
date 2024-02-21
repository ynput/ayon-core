import os

import pyblish.api

from ayon_core.hosts.hiero.api.otio import hiero_export


class CollectWorkfile(pyblish.api.InstancePlugin):
    """Collect the otio timeline"""

    families = ["workfile"]
    label = "Collect OTIO Timeline"
    order = pyblish.api.CollectorOrder - 0.49

    def process(self, instance):
        otio_timeline = hiero_export.create_otio_timeline()
        instance.data["otio_timeline"] = otio_timeline
