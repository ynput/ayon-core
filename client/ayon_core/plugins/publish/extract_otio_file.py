import os

import pyblish.api

from ayon_core.pipeline import publish


class ExtractOTIOFile(publish.Extractor):
    """Prepare workfile representation from OTIO file.

    Uses the OTIO timeline stored in context.data["otioTimeline"] to create
        workfile representation.

    """
    label = "Extract OTIO workfile"
    order = pyblish.api.ExtractorOrder - 0.45
    families = ["otio.timeline.workfile"]

    HAS_RUN_KEY = "__ExtractOTIOFile_Run__"

    def process(self, instance):
        # Not all hosts can import this module.
        import opentimelineio as otio

        # Mark instance for 'ExtractOTIOWorkfileOld'
        instance.data[self.HAS_RUN_KEY] = True
        if not instance.context.data.get("otioTimeline"):
            return
        # create representation data
        if "representations" not in instance.data:
            instance.data["representations"] = []

        name = instance.data["name"]
        staging_dir = self.staging_dir(instance)

        otio_timeline = instance.context.data["otioTimeline"]
        # create otio timeline representation
        otio_file_name = name + ".otio"
        otio_file_path = os.path.join(staging_dir, otio_file_name)
        otio.adapters.write_to_file(otio_timeline, otio_file_path)

        representation_otio = {
            'name': "otio",
            'ext': "otio",
            'files': otio_file_name,
            "stagingDir": staging_dir,
        }

        instance.data["representations"].append(representation_otio)

        self.log.info("Added OTIO file representation: {}".format(
            representation_otio))


class ExtractOTIOFileOld(ExtractOTIOFile):
    label = "Extract OTIO file (old)"
    order = ExtractOTIOFile.order + 0.00001
    families = ["workfile"]
    hosts = ["resolve", "hiero", "traypublisher"]

    def process(self, instance):
        if instance.data.pop(ExtractOTIOFile.HAS_RUN_KEY, False) is True:
            self.log.debug("Skipping, ExtractOTIOFile has run.")
            return
        self.log.debug("Using old ExtractOTIOFile plugin")
        super().process(instance)
