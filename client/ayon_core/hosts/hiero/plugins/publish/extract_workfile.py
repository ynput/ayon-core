import os
import pyblish.api

from ayon_core.pipeline import publish
from openpype.hosts.hiero.api import lib

import hiero
import tempfile

from qtpy.QtGui import QPixmap


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

        # asset = instance.context.data["folderPath"]
        # asset_name = asset.split("/")[-1]

        active_timeline = hiero.ui.activeSequence()
        # project = active_timeline.project()

        # adding otio timeline to context
        # otio_timeline = hiero_export.create_otio_timeline()
        # otio_timeline = instance.data["otioTimeline"]

        # get workfile thumbnail paths
        tmp_staging = tempfile.mkdtemp(prefix="pyblish_tmp_")
        thumbnail_name = "workfile_thumbnail.png"
        thumbnail_path = os.path.join(tmp_staging, thumbnail_name)

        # search for all windows with name of actual sequence
        _windows = [w for w in hiero.ui.windowManager().windows()
                    if active_timeline.name() in w.windowTitle()]

        # export window to thumb path
        QPixmap.grabWidget(_windows[-1]).save(thumbnail_path, 'png')

        # thumbnail
        thumb_representation = {
            'files': thumbnail_name,
            'stagingDir': tmp_staging,
            'name': "thumbnail",
            'thumbnail': True,
            'ext': "png"
        }

        name = instance.data["name"]
        project = hiero.ui.activeProject()
        staging_dir = self.staging_dir(instance)

        ext = ".hrox"
        filename = name + ext
        filepath = os.path.normpath(
            os.path.join(staging_dir, filename))

        # write out the workfile
        path_previous = project.path()
        project.saveAs(filepath)
        project.setPath(path_previous)

        # create workfile representation
        representation = {
            'name': ext.lstrip("."),
            'ext': ext.lstrip("."),
            'files': filename,
            "stagingDir": staging_dir,
        }
        representations = instance.data.setdefault("representations", [])
        representations.append(representation)
        representations.append(thumb_representation)

        self.log.debug(
            "Added hiero file representation: {}".format(representation)
        )