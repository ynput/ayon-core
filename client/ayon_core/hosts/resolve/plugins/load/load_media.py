import json
import copy
from collections import defaultdict
from typing import Union

from openpype.client import (
    get_version_by_id,
    get_last_version_by_subset_id,
)
from openpype.pipeline import (
    LoaderPlugin,
    get_representation_context,
    get_representation_path,
    registered_host
)
from openpype.pipeline.context_tools import get_current_project_name
from openpype.hosts.resolve.api import lib
from openpype.hosts.resolve.api.pipeline import AVALON_CONTAINER_ID
from openpype.lib.transcoding import (
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS
)
from openpype.lib import BoolDef


def find_clip_usage(media_pool_item, project=None):
    """Return all Timeline Items in the project using the Media Pool Item.

    Each entry in the list is a tuple of Timeline and TimelineItem so that
    it's easy to know which Timeline the TimelineItem belongs to.

    Arguments:
        media_pool_item (MediaPoolItem): The Media Pool Item to search for.
        project (Project): The resolve project the media pool item resides in.

    Returns:
        List[Tuple[Timeline, TimelineItem]]: A 2-tuple of a timeline with
            the timeline item.

    """
    usage = int(media_pool_item.GetClipProperty("Usage"))
    if not usage:
        return []

    if project is None:
        project = lib.get_current_project()

    matching_items = []
    unique_id = media_pool_item.GetUniqueId()
    for timeline_idx in range(project.GetTimelineCount()):
        timeline = project.GetTimelineByIndex(timeline_idx+1)

        # Consider audio and video tracks
        for track_type in ["video", "audio"]:
            for track_idx in range(timeline.GetTrackCount(track_type)):
                timeline_items = timeline.GetItemListInTrack(track_type,
                                                             track_idx+1)
                for timeline_item in timeline_items:
                    timeline_item_mpi = timeline_item.GetMediaPoolItem()
                    if not timeline_item_mpi:
                        continue

                    if timeline_item_mpi.GetUniqueId() == unique_id:
                        matching_items.append((timeline, timeline_item))
                        usage -= 1
                        if usage <= 0:
                            # If there should be no usage left after this found
                            # entry we return early
                            return matching_items

    return matching_items


class LoadMedia(LoaderPlugin):
    """Load a subset as media pool item."""

    families = ["render2d", "source", "plate", "render", "review"]

    representations = ["*"]
    extensions = set(
        ext.lstrip(".") for ext in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS)
    )

    label = "Load media"
    order = -20
    icon = "code-fork"
    color = "orange"

    options = [
        BoolDef(
            "load_to_timeline",
            label="Load to timeline",
            default=True,
            tooltip="Whether on load to automatically add it to the current "
                    "timeline"
        ),
        BoolDef(
            "load_once",
            label="Re-use existing",
            default=True,
            tooltip="When enabled - if this particular version is already"
                    "loaded it will not be loaded again but will be re-used."
        )
    ]

    # for loader multiselection
    timeline = None

    # presets
    clip_color_last = "Olive"
    clip_color = "Orange"

    bin_path = "Loader/{representation[context][hierarchy]}/{asset[name]}"

    def load(self, context, name, namespace, options):

        # For loading multiselection, we store timeline before first load
        # because the current timeline can change with the imported media.
        if self.timeline is None:
            self.timeline = lib.get_current_timeline()

        representation = context["representation"]

        project = lib.get_current_project()
        media_pool = project.GetMediaPool()

        # Allow to use an existing media pool item and re-use it
        item = None
        if options.get("load_once", True):
            host = registered_host()
            repre_id = str(context["representation"]["_id"])
            for container in host.ls():
                if container["representation"] != repre_id:
                    continue

                if container["loader"] != self.__class__.__name__:
                    continue

                print(f"Re-using existing container: {container}")
                item = container["_item"]

        if item is None:
            # Create or set the bin folder, we add it in there
            # If bin path is not set we just add into the current active bin
            if self.bin_path:
                bin_path = self.bin_path.format(**context)
                folder = lib.create_bin(
                    name=bin_path,
                    root=media_pool.GetRootFolder(),
                    set_as_current=False
                )
                media_pool.SetCurrentFolder(folder)

            # Import media
            path = self._get_filepath(representation)
            items = media_pool.ImportMedia([path])

            assert len(items) == 1, "Must import only one media item"
            item = items[0]

            self._set_metadata(media_pool_item=item,
                               context=context)

            data = self._get_container_data(representation)

            # Add containerise data only needed on first load
            data.update({
                "schema": "openpype:container-2.0",
                "id": AVALON_CONTAINER_ID,
                "loader": str(self.__class__.__name__),
            })

            item.SetMetadata(lib.pype_tag_name, json.dumps(data))

        # Always update clip color - even if re-using existing clip
        color = self.get_item_color(representation)
        item.SetClipColor(color)

        if options.get("load_to_timeline", True):
            timeline = options.get("timeline", self.timeline)
            if timeline:
                # Add media to active timeline
                lib.create_timeline_item(
                    media_pool_item=item,
                    timeline=timeline
                )

    def switch(self, container, representation):
        self.update(container, representation)

    def update(self, container, representation):
        # Update MediaPoolItem filepath and metadata
        item = container["_item"]

        # Get the existing metadata before we update because the
        # metadata gets removed
        data = json.loads(item.GetMetadata(lib.pype_tag_name))

        # Update path
        path = self._get_filepath(representation)
        item.ReplaceClip(path)

        # Update the metadata
        update_data = self._get_container_data(representation)
        data.update(update_data)
        item.SetMetadata(lib.pype_tag_name, json.dumps(data))

        context = get_representation_context(representation)
        self._set_metadata(media_pool_item=item, context=context)

        # Update the clip color
        color = self.get_item_color(representation)
        item.SetClipColor(color)

    def remove(self, container):
        # Remove MediaPoolItem entry
        project = lib.get_current_project()
        media_pool = project.GetMediaPool()
        item = container["_item"]

        # Delete any usages of the media pool item so there's no trail
        # left in existing timelines. Currently only the media pool item
        # gets removed which fits the Resolve workflow but is confusing
        # artists
        usage = find_clip_usage(media_pool_item=item, project=project)
        if usage:
            # Group all timeline items per timeline, so we can delete the clips
            # in the timeline at once. The Resolve objects are not hashable, so
            # we need to store them in the dict by id
            usage_by_timeline = defaultdict(list)
            timeline_by_id = {}
            for timeline, timeline_item in usage:
                timeline_id = timeline.GetUniqueId()
                timeline_by_id[timeline_id] = timeline
                usage_by_timeline[timeline.GetUniqueId()].append(timeline_item)

            for timeline_id, timeline_items in usage_by_timeline.items():
                timeline = timeline_by_id[timeline_id]
                timeline.DeleteClips(timeline_items)

        # Delete the media pool item
        media_pool.DeleteClips([item])

    def _get_container_data(self, representation):
        """Return metadata related to the representation and version."""

        # load clip to timeline and get main variables
        project_name = get_current_project_name()
        version = get_version_by_id(project_name, representation["parent"])
        version_data = version.get("data", {})
        version_name = version.get("name", None)
        colorspace = version_data.get("colorspace", None)

        # add additional metadata from the version to imprint Avalon knob
        add_keys = [
            "frameStart", "frameEnd", "source", "author",
            "fps", "handleStart", "handleEnd"
        ]
        data = {
            key: version_data.get(key, str(None)) for key in add_keys
        }

        # add variables related to version context
        data.update({
            "representation": str(representation["_id"]),
            "version": version_name,
            "colorspace": colorspace,
        })

        return data

    @classmethod
    def get_item_color(cls, representation) -> str:
        """Return item color name.

        Coloring depends on whether representation is the latest version.
        """
        # Compare version with last version
        project_name = get_current_project_name()
        version = get_version_by_id(
            project_name,
            representation["parent"],
            fields=["name", "parent"]
        )
        last_version = get_last_version_by_subset_id(
            project_name,
            version["parent"],
            fields=["name"]
        ) or {}

        # set clip colour
        if version.get("name") == last_version.get("name"):
            return cls.clip_color_last
        else:
            return cls.clip_color

    def _set_metadata(self, media_pool_item, context: dict):
        """Set Media Pool Item Clip Properties"""

        # Set the timecode for the loaded clip if Resolve doesn't parse it
        # correctly from the input. An image sequence will have timecode
        # parsed from its frame range, we will want to preserve that.
        # TODO: Setting the Start TC breaks existing clips on update
        #   See: https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=197327
        #   Once that's resolved we should enable this
        # start_tc = media_pool_item.GetClipProperty("Start TC")
        # if start_tc == "00:00:00:00":
        #     from openpype.pipeline.editorial import frames_to_timecode
        #     # Assume no timecode was detected from the source media
        #
        #     fps = float(media_pool_item.GetClipProperty("FPS"))
        #     handle_start = context["version"]["data"].get("handleStart", 0)
        #     frame_start = context["version"]["data"].get("frameStart", 0)
        #     frame_start_handle = frame_start - handle_start
        #     timecode = frames_to_timecode(frame_start_handle, fps)
        #
        #     if timecode != start_tc:
        #         media_pool_item.SetClipProperty("Start TC", timecode)

        # Set more clip metadata based on the loaded clip's context
        metadata = {
            "Clip Name": "{asset[name]} {subset[name]} "
                         "v{version[name]:03d} ({representation[name]})",
            "Shot": "{asset[name]}",
            "Take": "{subset[name]} v{version[name]:03d}",
            "Comments": "{version[data][comment]}"
        }
        for clip_property, value in metadata.items():
            media_pool_item.SetClipProperty(clip_property,
                                            value.format_map(context))

    def _get_filepath(self, representation: dict) -> Union[str, dict]:

        is_sequence = bool(representation["context"].get("frame"))
        if not is_sequence:
            return get_representation_path(representation)

        context = get_representation_context(representation)
        version = context["version"]

        # Get the start and end frame of the image sequence, incl. handles
        frame_start = version["data"].get("frameStart", 0)
        frame_end = version["data"].get("frameEnd", 0)
        handle_start = version["data"].get("handleStart", 0)
        handle_end = version["data"].get("handleEnd", 0)
        frame_start_handle = frame_start - handle_start
        frame_end_handle = frame_end + handle_end
        padding = len(representation["context"].get("frame"))

        # We format the frame number to the required token. To do so
        # we in-place change the representation context data to format the path
        # with that replaced data
        representation = copy.deepcopy(representation)
        representation["context"]["frame"] = f"%0{padding}d"
        path = get_representation_path(representation)

        # See Resolve API, to import for example clip "file_[001-100].dpx":
        # ImportMedia([{"FilePath":"file_%03d.dpx",
        #               "StartIndex":1,
        #               "EndIndex":100}])
        return {
            "FilePath": path,
            "StartIndex": frame_start_handle,
            "EndIndex": frame_end_handle
        }
