import pyblish.api
from pprint import pformat

from ayon_core.pipeline import get_current_asset_name

from ayon_core.hosts.resolve import api as rapi
from ayon_core.hosts.resolve.otio import davinci_export


class PrecollectWorkfile(pyblish.api.ContextPlugin):
    """Precollect the current working file into context"""

    label = "Precollect Workfile"
    order = pyblish.api.CollectorOrder - 0.5

    def process(self, context):
        current_asset_name = get_current_asset_name()
        asset_name = current_asset_name.split("/")[-1]

        product_name = "workfileMain"
        resolve_project = rapi.get_current_resolve_project()
        fps = resolve_project.GetSetting("timelineFrameRate")
        video_tracks = rapi.get_video_track_names()

        # adding otio timeline to context
        otio_timeline = davinci_export.create_otio_timeline(resolve_project)

        instance_data = {
            "name": "{}_{}".format(asset_name, product_name),
            "label": "{} {}".format(current_asset_name, product_name),
            "item": resolve_project,
            "folderPath": current_asset_name,
            "productName": product_name,
            "productType": "workfile",
            "family": "workfile",
            "families": []
        }

        # create instance with workfile
        instance = context.create_instance(**instance_data)

        # update context with main project attributes
        context_data = {
            "activeProject": resolve_project,
            "otioTimeline": otio_timeline,
            "videoTracks": video_tracks,
            "currentFile": resolve_project.GetName(),
            "fps": fps,
        }
        context.data.update(context_data)

        self.log.info("Creating instance: {}".format(instance))
        self.log.debug("__ instance.data: {}".format(pformat(instance.data)))
        self.log.debug("__ context_data: {}".format(pformat(context_data)))
