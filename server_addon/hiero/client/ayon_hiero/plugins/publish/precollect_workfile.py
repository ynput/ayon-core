import os
import tempfile
from pprint import pformat

import pyblish.api
from qtpy.QtGui import QPixmap

import hiero.ui

from ayon_hiero.api.otio import hiero_export


class PrecollectWorkfile(pyblish.api.ContextPlugin):
    """Inject the current working file into context"""

    label = "Precollect Workfile"
    order = pyblish.api.CollectorOrder - 0.491

    def process(self, context):
        folder_path = context.data["folderPath"]
        folder_name = folder_path.split("/")[-1]

        active_timeline = hiero.ui.activeSequence()
        project = active_timeline.project()
        fps = active_timeline.framerate().toFloat()

        # adding otio timeline to context
        otio_timeline = hiero_export.create_otio_timeline()

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

        # get workfile paths
        current_file = project.path()
        staging_dir, base_name = os.path.split(current_file)

        # creating workfile representation
        workfile_representation = {
            'name': 'hrox',
            'ext': 'hrox',
            'files': base_name,
            "stagingDir": staging_dir,
        }
        product_type = "workfile"
        instance_data = {
            "label": "{} - {}Main".format(
                folder_path, product_type),
            "name": "{}_{}".format(folder_name, product_type),
            "folderPath": folder_path,
            # TODO use 'get_product_name'
            "productName": "{}{}Main".format(
                folder_name, product_type.capitalize()
            ),
            "item": project,
            "productType": product_type,
            "family": product_type,
            "families": [product_type],
            "representations": [workfile_representation, thumb_representation]
        }

        # create instance with workfile
        instance = context.create_instance(**instance_data)

        # update context with main project attributes
        context_data = {
            "activeProject": project,
            "activeTimeline": active_timeline,
            "otioTimeline": otio_timeline,
            "currentFile": current_file,
            "colorspace": self.get_colorspace(project),
            "fps": fps
        }
        self.log.debug("__ context_data: {}".format(pformat(context_data)))
        context.data.update(context_data)

        self.log.info("Creating instance: {}".format(instance))
        self.log.debug("__ instance.data: {}".format(pformat(instance.data)))
        self.log.debug("__ context_data: {}".format(pformat(context_data)))

    def get_colorspace(self, project):
        # get workfile's colorspace properties
        return {
            "useOCIOEnvironmentOverride": project.useOCIOEnvironmentOverride(),
            "lutSetting16Bit": project.lutSetting16Bit(),
            "lutSetting8Bit": project.lutSetting8Bit(),
            "lutSettingFloat": project.lutSettingFloat(),
            "lutSettingLog": project.lutSettingLog(),
            "lutSettingViewer": project.lutSettingViewer(),
            "lutSettingWorkingSpace": project.lutSettingWorkingSpace(),
            "lutUseOCIOForExport": project.lutUseOCIOForExport(),
            "ocioConfigName": project.ocioConfigName(),
            "ocioConfigPath": project.ocioConfigPath()
        }
