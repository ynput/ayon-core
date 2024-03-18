import pyblish.api

from ayon_core.hosts.resolve import api as rapi
from ayon_core.hosts.resolve.otio import davinci_export


class CollectResolveProject(pyblish.api.ContextPlugin):
    """Collect the current Resolve project and current timeline data"""

    label = "Collect Project and Current Timeline"
    order = pyblish.api.CollectorOrder - 0.499

    def process(self, context):
        resolve_project = rapi.get_current_resolve_project()
        timeline = resolve_project.GetCurrentTimeline()
        fps = timeline.GetSetting("timelineFrameRate")

        video_tracks = rapi.get_video_track_names()

        # adding otio timeline to context
        otio_timeline = davinci_export.create_otio_timeline(resolve_project)

        # update context with main project attributes
        context.data.update({
            # project
            "activeProject": resolve_project,
            "currentFile": resolve_project.GetName(),
            # timeline
            "otioTimeline": otio_timeline,
            "videoTracks": video_tracks,
            "fps": fps,
        })
