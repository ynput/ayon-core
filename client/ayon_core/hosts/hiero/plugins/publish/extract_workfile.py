import os
import pyblish.api

from ayon_core.pipeline import publish
from openpype.hosts.hiero.api import lib


class ExtractWorkfile(publish.Extractor):
    """
    Extractor export Hiero workfile representation
    """

    label = "Extract Workfile"
    order = pyblish.api.ExtractorOrder
    families = ["workfile"]
    hosts = ["hiero"]

    def process(self, instance):
        # create representation data
        if "representations" not in instance.data:
            instance.data["representations"] = []

        name = instance.data["name"]
        project = instance.context.data["activeProject"]
        staging_dir = self.staging_dir(instance)

        ext = ".hrox"
        filename = name + ext
        filepath = os.path.normpath(
            os.path.join(staging_dir, filename))

        # write out the workfile
        project.saveAs(filepath)

        # create workfile representation
        representation = {
            'name': ext.lstrip("."),
            'ext': ext.lstrip("."),
            'files': filename,
            "stagingDir": staging_dir,
        }
        representations = instance.data.setdefault("representations", [])
        representations.append(representation )

        self.log.debug(
            "Added hiero file representation: {}".format(representation)
        )