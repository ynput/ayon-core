import os

import pyblish.api

from ayon_core.hosts.hiero.api.otio import hiero_export

import hiero

class CollectOTIOTimeline(pyblish.api.ContextPlugin):
    """Inject the otio timeline"""

    label = "Collect OTIO Timeline"
    order = pyblish.api.CollectorOrder - 0.491

    def process(self, context):
        otio_timeline = hiero_export.create_otio_timeline()

        active_timeline = hiero.ui.activeSequence()
        project = active_timeline.project()
        fps = active_timeline.framerate().toFloat()

        # current_file = project.path()

        context_data = {
            "activeProject": project,
            "activeTimeline": active_timeline,
            "otioTimeline": otio_timeline,
            # "currentFile": current_file,
            "colorspace": self.get_colorspace(project),
            "fps": fps
        }
        context.data.update(context_data)

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
