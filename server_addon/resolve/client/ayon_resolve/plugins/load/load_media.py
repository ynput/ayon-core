import json
import contextlib
from pathlib import Path
from collections import defaultdict
from typing import Union, List, Optional, TypedDict, Tuple

from ayon_api import version_is_latest
from ayon_core.lib import StringTemplate
from ayon_core.pipeline.colorspace import get_remapped_colorspace_to_native
from ayon_core.pipeline import (
    Anatomy,
    LoaderPlugin,
    get_representation_path,
    registered_host
)
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.lib.transcoding import (
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS
)
from ayon_core.lib import BoolDef
from ayon_resolve.api import lib
from ayon_resolve.api.pipeline import AVALON_CONTAINER_ID


FRAME_SPLITTER = "__frame_splitter__"


class MetadataEntry(TypedDict):
    """Metadata entry is dict with {"name": "key", "value: "value"}"""
    name: str
    value: str


@contextlib.contextmanager
def project_color_science_mode(project=None, mode="davinciYRGBColorManagedv2"):
    """Set project color science mode during context.

    This is especially useful as context for setting the colorspace for media
    pool items, because when Resolve is not set to `davinciYRGBColorManagedv2`
    it fails to set its "Input Color Space" clip property even though it is
    accessible and settable via the Resolve User Interface.

    Args
        project (Project): The active Resolve Project.
        mode (Optional[str]): The color science mode to apply during the
            context. Defaults to 'davinciYRGBColorManagedv2'

    See Also:
        https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=197441
    """

    if project is None:
        project = lib.get_current_project()

    original_mode = project.GetSetting("colorScienceMode")
    if original_mode != mode:
        project.SetSetting("colorScienceMode", mode)
    try:
        yield
    finally:
        if project.GetSetting("colorScienceMode") != original_mode:
            project.SetSetting("colorScienceMode", original_mode)


def set_colorspace(media_pool_item,
                   colorspace,
                   mode="davinciYRGBColorManagedv2"):
    """Set MediaPoolItem colorspace.

    This implements a workaround that you cannot set the input colorspace
    unless the Resolve project's color science mode is set to
    `davinciYRGBColorManagedv2`.

    Args:
        media_pool_item (MediaPoolItem): The media pool item.
        colorspace (str): The colorspace to apply.
        mode (Optional[str]): The Resolve project color science mode to be in
            while setting the colorspace.
            Defaults to 'davinciYRGBColorManagedv2'

    Returns:
        bool: Whether applying the colorspace succeeded.
    """
    with project_color_science_mode(mode=mode):
        return media_pool_item.SetClipProperty("Input Color Space", colorspace)


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
        timeline = project.GetTimelineByIndex(timeline_idx + 1)

        # Consider audio and video tracks
        for track_type in ["video", "audio"]:
            for track_idx in range(timeline.GetTrackCount(track_type)):
                timeline_items = timeline.GetItemListInTrack(track_type,
                                                             track_idx + 1)
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
    """Load product as media pool item."""

    product_types = {"render2d", "source", "plate", "render", "review"}

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
    clip_color_old = "Orange"

    media_pool_bin_path = "Loader/{folder[path]}"

    metadata: List[MetadataEntry] = []

    # cached on apply settings
    _host_imageio_settings = None

    @classmethod
    def apply_settings(cls, project_settings):
        super(LoadMedia, cls).apply_settings(project_settings)
        cls._host_imageio_settings = project_settings["resolve"]["imageio"]

    def load(self, context, name, namespace, options):

        # For loading multiselection, we store timeline before first load
        # because the current timeline can change with the imported media.
        if self.timeline is None:
            self.timeline = lib.get_current_timeline()

        representation = context["representation"]
        self._project_name = context["project"]["name"]

        project = lib.get_current_project()
        media_pool = project.GetMediaPool()

        # Allow to use an existing media pool item and re-use it
        item = None
        if options.get("load_once", True):
            host = registered_host()
            repre_id = context["representation"]["id"]
            for container in host.ls():
                if container["representation"] != repre_id:
                    continue

                if container["loader"] != self.__class__.__name__:
                    continue

                print(f"Re-using existing container: {container}")
                item = container["_item"]

        if item is None:
            item = self._import_media_to_bin(context, media_pool, representation)
        # Always update clip color - even if re-using existing clip
        color = self.get_item_color(context)
        item.SetClipColor(color)

        if options.get("load_to_timeline", True):
            timeline = options.get("timeline", self.timeline)
            if timeline:
                # Add media to active timeline
                lib.create_timeline_item(
                    media_pool_item=item,
                    timeline=timeline
                )

    def _import_media_to_bin(
        self, context, media_pool, representation
    ):
        """Import media to Resolve Media Pool.

        Also create a bin if `media_pool_bin_path` is set.

        Args:
            context (dict): The context dictionary.
            media_pool (resolve.MediaPool): The Resolve Media Pool.
            representation (dict): The representation data.

        Returns:
            resolve.MediaPoolItem: The imported media pool item.
        """
        # Create or set the bin folder, we add it in there
        # If bin path is not set we just add into the current active bin
        if self.media_pool_bin_path:
            media_pool_bin_path = StringTemplate(
                self.media_pool_bin_path).format_strict(context)

            folder = lib.create_bin(
                # double slashes will create unconnected folders
                name=media_pool_bin_path.replace("//", "/"),
                root=media_pool.GetRootFolder(),
                set_as_current=False
            )
            media_pool.SetCurrentFolder(folder)

        # Import media
        # Resolve API: ImportMedia function requires a list of dictionaries
        # with keys "FilePath", "StartIndex" and "EndIndex" for sequences
        # but only string with absolute path for single files.
        is_sequence, file_info = self._get_file_info(context)
        items = (
            media_pool.ImportMedia([file_info])
            if is_sequence
            else media_pool.ImportMedia([file_info["FilePath"]])
        )
        assert len(items) == 1, "Must import only one media item"

        result = items[0]

        self._set_metadata(result, context)
        self._set_colorspace_from_representation(result, representation)

        data = self._get_container_data(context)

        # Add containerise data only needed on first load
        data.update({
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "loader": str(self.__class__.__name__),
        })

        result.SetMetadata(lib.pype_tag_name, json.dumps(data))

        return result

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        # Update MediaPoolItem filepath and metadata
        item = container["_item"]

        # Get the existing metadata before we update because the
        # metadata gets removed
        data = json.loads(item.GetMetadata(lib.pype_tag_name))

        # Get metadata to preserve after the clip replacement
        # TODO: Maybe preserve more, like LUT, Alpha Mode, Input Sizing Preset
        colorspace_before = item.GetClipProperty("Input Color Space")

        # Update path
        path = get_representation_path(context["representation"])
        success = item.ReplaceClip(path)
        if not success:
            raise RuntimeError(
                f"Failed to replace media pool item clip to filepath: {path}"
            )

        # Update the metadata
        update_data = self._get_container_data(context)
        data.update(update_data)
        item.SetMetadata(lib.pype_tag_name, json.dumps(data))

        self._set_metadata(media_pool_item=item, context=context)
        self._set_colorspace_from_representation(
            item,
            representation=context["representation"]
        )

        # If no specific colorspace is set then we want to preserve the
        # colorspace a user might have set before the clip replacement
        if (
                item.GetClipProperty("Input Color Space") == "Project"
                and colorspace_before != "Project"
        ):
            result = set_colorspace(item, colorspace_before)
            if not result:
                self.log.warning(
                    f"Failed to re-apply colorspace: {colorspace_before}."
                )

        # Update the clip color
        color = self.get_item_color(context)
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

    def _get_container_data(self, context: dict) -> dict:
        """Return metadata related to the representation and version."""

        # add additional metadata from the version to imprint AYON knob
        version = context["version"]
        data = {}

        # version.attrib
        for key in [
            "frameStart", "frameEnd",
            "handleStart", "handleEnd",
            "source", "fps", "colorSpace"
        ]:
            data[key] = version["attrib"][key]

        # version.data
        for key in ["author"]:
            data[key] = version["data"][key]

        # add variables related to version context
        data.update({
            "representation": context["representation"]["id"],
            "version": version["name"],
        })

        return data

    @classmethod
    def get_item_color(cls, context: dict) -> str:
        """Return item color name.

        Coloring depends on whether representation is the latest version.
        """
        # Compare version with last version
        # set clip colour
        if version_is_latest(project_name=context["project"]["name"],
                             version_id=context["version"]["id"]):
            return cls.clip_color_last
        else:
            return cls.clip_color_old

    def _set_metadata(self, media_pool_item, context: dict):
        """Set Media Pool Item Clip Properties"""

        # Set more clip metadata based on the loaded clip's context
        for meta_item in self.metadata:
            clip_property = meta_item["name"]
            value = meta_item["value"]
            value_formatted = StringTemplate(value).format_strict(context)
            media_pool_item.SetClipProperty(clip_property, value_formatted)

    def _get_file_info(self, context: dict) -> Tuple[bool, Union[str, dict]]:
        """Return file info for Resolve ImportMedia.

        Args:
            context (dict): The context dictionary.

        Returns:
            Tuple[bool, Union[str, dict]]: A tuple of whether the file is a
                sequence and the file info dictionary.
        """

        representation = context["representation"]
        anatomy = Anatomy(self._project_name)

        # Get path to representation with correct frame number
        repre_path = get_representation_path_with_anatomy(
            representation, anatomy)

        first_frame = representation["context"].get("frame")

        is_sequence = False
        # is not sequence
        if first_frame is None:
            return (
                is_sequence, {"FilePath": repre_path}
            )

        # This is sequence
        is_sequence = True
        repre_files = [
            file["path"].format(root=anatomy.roots)
            for file in representation["files"]
        ]

        # Change frame in representation context to get path with frame
        #   splitter.
        representation["context"]["frame"] = FRAME_SPLITTER
        frame_repre_path = get_representation_path_with_anatomy(
            representation, anatomy
        )
        frame_repre_path = Path(frame_repre_path)
        repre_dir, repre_filename = (
            frame_repre_path.parent, frame_repre_path.name)
        # Get sequence prefix and suffix
        file_prefix, file_suffix = repre_filename.split(FRAME_SPLITTER)
        # Get frame number from path as string to get frame padding
        frame_str = str(repre_path)[len(file_prefix):][:len(file_suffix)]
        frame_padding = len(frame_str)

        file_name = f"{file_prefix}%0{frame_padding}d{file_suffix}"

        abs_filepath = Path(repre_dir, file_name)

        start_index = int(first_frame)
        end_index = int(int(first_frame) + len(repre_files) - 1)

        # See Resolve API, to import for example clip "file_[001-100].dpx":
        # ImportMedia([{"FilePath":"file_%03d.dpx",
        #               "StartIndex":1,
        #               "EndIndex":100}])
        return (
            is_sequence,
            {
                "FilePath": abs_filepath.as_posix(),
                "StartIndex": start_index,
                "EndIndex": end_index,
            }
        )

    def _get_colorspace(self, representation: dict) -> Optional[str]:
        """Return Resolve native colorspace from OCIO colorspace data.

        Returns:
            Optional[str]: The Resolve native colorspace name, if any mapped.
        """

        data = representation.get("data", {}).get("colorspaceData", {})
        if not data:
            return

        ocio_colorspace = data["colorspace"]
        if not ocio_colorspace:
            return

        resolve_colorspace = get_remapped_colorspace_to_native(
            ocio_colorspace_name=ocio_colorspace,
            host_name="resolve",
            imageio_host_settings=self._host_imageio_settings
        )
        if resolve_colorspace:
            return resolve_colorspace
        else:
            self.log.warning(
                f"No mapping from OCIO colorspace '{ocio_colorspace}' "
                "found to a Resolve colorspace. "
                "Ignoring colorspace."
            )

    def _set_colorspace_from_representation(
            self, media_pool_item, representation: dict):
        """Set the colorspace for the media pool item.

        Args:
            media_pool_item (MediaPoolItem): The media pool item.
            representation (dict): The representation data.
        """
        # Set the Resolve Input Color Space for the media.
        colorspace = self._get_colorspace(representation)
        if colorspace:
            result = set_colorspace(media_pool_item, colorspace)
            if not result:
                self.log.warning(
                    f"Failed to apply colorspace: {colorspace}."
                )
