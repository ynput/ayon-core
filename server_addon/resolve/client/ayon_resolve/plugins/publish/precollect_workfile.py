import pyblish.api
from pprint import pformat

from ayon_core.pipeline import get_current_folder_path

from ayon_resolve import api as rapi
from ayon_resolve.otio import davinci_export


class PrecollectWorkfile(pyblish.api.ContextPlugin):
    """Precollect the current working file into context"""

    label = "Precollect Workfile"
    order = pyblish.api.CollectorOrder - 0.5

    def process(self, context):
        current_folder_path = get_current_folder_path()
        folder_name = current_folder_path.split("/")[-1]

        product_name = "workfileMain"
        project = rapi.get_current_project()
        fps = project.GetSetting("timelineFrameRate")
        video_tracks = rapi.get_video_track_names()

        # adding otio timeline to context
        otio_timeline = davinci_export.create_otio_timeline(project)

        instance_data = {
            "name": "{}_{}".format(folder_name, product_name),
            "label": "{} {}".format(current_folder_path, product_name),
            "item": project,
            "folderPath": current_folder_path,
            "productName": product_name,
            "productType": "workfile",
            "family": "workfile",
            "families": []
        }

        # create instance with workfile
        instance = context.create_instance(**instance_data)

        # update context with main project attributes
        context_data = {
            "activeProject": project,
            "otioTimeline": otio_timeline,
            "videoTracks": video_tracks,
            "currentFile": project.GetName(),
            "fps": fps,
        }
        context.data.update(context_data)

        self.log.info("Creating instance: {}".format(instance))
        self.log.debug("__ instance.data: {}".format(pformat(instance.data)))
        self.log.debug("__ context_data: {}".format(pformat(context_data)))
