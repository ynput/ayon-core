import os
from copy import deepcopy

import ayon_api
import opentimelineio as otio

from ayon_core.hosts.traypublisher.api.plugin import (
    TrayPublishCreator,
    HiddenTrayPublishCreator
)
from ayon_core.hosts.traypublisher.api.editorial import (
    ShotMetadataSolver
)
from ayon_core.pipeline import CreatedInstance
from ayon_core.lib import (
    get_ffprobe_data,
    convert_ffprobe_fps_value,

    FileDef,
    TextDef,
    NumberDef,
    EnumDef,
    BoolDef,
    UISeparatorDef,
    UILabelDef
)


CLIP_ATTR_DEFS = [
    EnumDef(
        "fps",
        items=[
            {"value": "from_selection", "label": "From selection"},
            {"value": 23.997, "label": "23.976"},
            {"value": 24, "label": "24"},
            {"value": 25, "label": "25"},
            {"value": 29.97, "label": "29.97"},
            {"value": 30, "label": "30"}
        ],
        label="FPS"
    ),
    NumberDef(
        "workfile_start_frame",
        default=1001,
        label="Workfile start frame"
    ),
    NumberDef(
        "handle_start",
        default=0,
        label="Handle start"
    ),
    NumberDef(
        "handle_end",
        default=0,
        label="Handle end"
    )
]


class EditorialClipInstanceCreatorBase(HiddenTrayPublishCreator):
    """Wrapper class for clip product type creators."""
    host_name = "traypublisher"

    def create(self, instance_data, source_data=None):
        product_name = instance_data["productName"]

        # Create new instance
        new_instance = CreatedInstance(
            self.product_type, product_name, instance_data, self
        )

        self._store_new_instance(new_instance)

        return new_instance

    def get_instance_attr_defs(self):
        return [
            BoolDef(
                "add_review_family",
                default=True,
                label="Review"
            )
        ]


class EditorialShotInstanceCreator(EditorialClipInstanceCreatorBase):
    """Shot product type class

    The shot metadata instance carrier.
    """
    identifier = "editorial_shot"
    product_type = "shot"
    label = "Editorial Shot"

    def get_instance_attr_defs(self):
        instance_attributes = [
            TextDef(
                "folderPath",
                label="Folder path"
            )
        ]
        instance_attributes.extend(CLIP_ATTR_DEFS)
        return instance_attributes


class EditorialPlateInstanceCreator(EditorialClipInstanceCreatorBase):
    """Plate product type class

    Plate representation instance.
    """
    identifier = "editorial_plate"
    product_type = "plate"
    label = "Editorial Plate"


class EditorialAudioInstanceCreator(EditorialClipInstanceCreatorBase):
    """Audio product type class

    Audio representation instance.
    """
    identifier = "editorial_audio"
    product_type = "audio"
    label = "Editorial Audio"


class EditorialReviewInstanceCreator(EditorialClipInstanceCreatorBase):
    """Review product type class

    Review representation instance.
    """
    identifier = "editorial_review"
    product_type = "review"
    label = "Editorial Review"


class EditorialSimpleCreator(TrayPublishCreator):
    """Editorial creator class

    Simple workflow creator. This creator only disecting input
    video file into clip chunks and then converts each to
    defined format defined Settings for each product preset.

    Args:
        TrayPublishCreator (Creator): Tray publisher plugin class
    """

    label = "Editorial Simple"
    product_type = "editorial"
    identifier = "editorial_simple"
    default_variants = [
        "main"
    ]
    description = "Editorial files to generate shots."
    detailed_description = """
Supporting publishing new shots to project
or updating already created. Publishing will create OTIO file.
"""
    icon = "fa.file"
    product_type_presets = []

    def __init__(self, *args, **kwargs):
        self._shot_metadata_solver = ShotMetadataSolver(self.log)
        super(EditorialSimpleCreator, self).__init__(*args, **kwargs)

    def apply_settings(self, project_settings):
        editorial_creators = deepcopy(
            project_settings["traypublisher"]["editorial_creators"]
        )
        creator_settings = editorial_creators.get(self.identifier)

        self._shot_metadata_solver.update_data(
            creator_settings["clip_name_tokenizer"],
            creator_settings["shot_rename"],
            creator_settings["shot_hierarchy"],
            creator_settings["shot_add_tasks"]
        )
        self.product_type_presets = creator_settings["product_type_presets"]
        default_variants = creator_settings.get("default_variants")
        if default_variants:
            self.default_variants = default_variants

    def create(self, product_name, instance_data, pre_create_data):
        allowed_product_type_presets = self._get_allowed_product_type_presets(
            pre_create_data)

        product_types = {
            item["product_type"]
            for item in self.product_type_presets
        }
        clip_instance_properties = {
            k: v
            for k, v in pre_create_data.items()
            if k != "sequence_filepath_data"
            if k not in product_types
        }

        folder_path = instance_data["folderPath"]
        folder_entity = ayon_api.get_folder_by_path(
            self.project_name, folder_path
        )

        if pre_create_data["fps"] == "from_selection":
            # get 'fps' from folder attributes
            fps = folder_entity["attrib"]["fps"]
        else:
            fps = float(pre_create_data["fps"])

        instance_data.update({
            "fps": fps
        })

        # get path of sequence
        sequence_path_data = pre_create_data["sequence_filepath_data"]
        media_path_data = pre_create_data["media_filepaths_data"]

        sequence_paths = self._get_path_from_file_data(
            sequence_path_data, multi=True)
        media_path = self._get_path_from_file_data(media_path_data)

        first_otio_timeline = None
        for seq_path in sequence_paths:
            # get otio timeline
            otio_timeline = self._create_otio_timeline(
                seq_path, fps)

            # Create all clip instances
            clip_instance_properties.update({
                "fps": fps,
                "variant": instance_data["variant"]
            })

            # create clip instances
            self._get_clip_instances(
                folder_entity,
                otio_timeline,
                media_path,
                clip_instance_properties,
                allowed_product_type_presets,
                os.path.basename(seq_path),
                first_otio_timeline,
            )

            if not first_otio_timeline:
                # assign otio timeline for multi file to layer
                first_otio_timeline = otio_timeline

        # create otio editorial instance
        self._create_otio_instance(
            product_name,
            instance_data,
            seq_path,
            media_path,
            first_otio_timeline
        )

    def _create_otio_instance(
        self,
        product_name,
        data,
        sequence_path,
        media_path,
        otio_timeline
    ):
        """Otio instance creating function

        Args:
            product_name (str): Product name.
            data (dict): instance data
            sequence_path (str): path to sequence file
            media_path (str): path to media file
            otio_timeline (otio.Timeline): otio timeline object
        """
        # Pass precreate data to creator attributes
        data.update({
            "sequenceFilePath": sequence_path,
            "editorialSourcePath": media_path,
            "otioTimeline": otio.adapters.write_to_string(otio_timeline)
        })
        new_instance = CreatedInstance(
            self.product_type, product_name, data, self
        )
        self._store_new_instance(new_instance)

    def _create_otio_timeline(self, sequence_path, fps):
        """Creating otio timeline from sequence path

        Args:
            sequence_path (str): path to sequence file
            fps (float): frame per second

        Returns:
            otio.Timeline: otio timeline object
        """
        # get editorial sequence file into otio timeline object
        extension = os.path.splitext(sequence_path)[1]

        kwargs = {}
        if extension == ".edl":
            # EDL has no frame rate embedded so needs explicit
            # frame rate else 24 is assumed.
            kwargs["rate"] = fps
            kwargs["ignore_timecode_mismatch"] = True

        return otio.adapters.read_from_file(sequence_path, **kwargs)

    def _get_path_from_file_data(self, file_path_data, multi=False):
        """Converting creator path data to single path string

        Args:
            file_path_data (FileDefItem): creator path data inputs
            multi (bool): switch to multiple files mode

        Raises:
            FileExistsError: in case nothing had been set

        Returns:
            str: path string
        """
        return_path_list = []


        if isinstance(file_path_data, list):
            return_path_list = [
                os.path.join(f["directory"], f["filenames"][0])
                for f in file_path_data
            ]

        if not return_path_list:
            raise FileExistsError(
                f"File path was not added: {file_path_data}")

        return return_path_list if multi else return_path_list[0]

    def _get_clip_instances(
        self,
        folder_entity,
        otio_timeline,
        media_path,
        instance_data,
        product_type_presets,
        sequence_file_name,
        first_otio_timeline=None
    ):
        """Helping function for creating clip instance

        Args:
            folder_entity (dict[str, Any]): Folder entity.
            otio_timeline (otio.Timeline): otio timeline object
            media_path (str): media file path string
            instance_data (dict): clip instance data
            product_type_presets (list): list of dict settings product presets
        """

        tracks = [
            track for track in otio_timeline.each_child(
                descended_from_type=otio.schema.Track)
            if track.kind == "Video"
        ]

        # media data for audio stream and reference solving
        media_data = self._get_media_source_metadata(media_path)

        for track in tracks:
            # set track name
            track.name = f"{sequence_file_name} - {otio_timeline.name}"

            try:
                track_start_frame = (
                    abs(track.source_range.start_time.value)
                )
                track_start_frame -= self.timeline_frame_start
            except AttributeError:
                track_start_frame = 0

            for otio_clip in track.each_child():
                if not self._validate_clip_for_processing(otio_clip):
                    continue

                # get available frames info to clip data
                self._create_otio_reference(otio_clip, media_path, media_data)

                # convert timeline range to source range
                self._restore_otio_source_range(otio_clip)

                base_instance_data = self._get_base_instance_data(
                    otio_clip,
                    instance_data,
                    track_start_frame,
                    folder_entity
                )

                parenting_data = {
                    "instance_label": None,
                    "instance_id": None
                }

                for product_type_preset in product_type_presets:
                    # exclude audio product type if no audio stream
                    if (
                        product_type_preset["product_type"] == "audio"
                        and not media_data.get("audio")
                    ):
                        continue

                    instance = self._make_product_instance(
                        otio_clip,
                        product_type_preset,
                        deepcopy(base_instance_data),
                        parenting_data
                    )

            # add track to first otioTimeline if it is in input args
            if first_otio_timeline:
                first_otio_timeline.tracks.append(deepcopy(track))

    def _restore_otio_source_range(self, otio_clip):
        """Infusing source range.

        Otio clip is missing proper source clip range so
        here we add them from from parent timeline frame range.

        Args:
            otio_clip (otio.Clip): otio clip object
        """
        otio_clip.source_range = otio_clip.range_in_parent()

    def _create_otio_reference(
        self,
        otio_clip,
        media_path,
        media_data
    ):
        """Creating otio reference at otio clip.

        Args:
            otio_clip (otio.Clip): otio clip object
            media_path (str): media file path string
            media_data (dict): media metadata
        """
        start_frame = media_data["start_frame"]
        frame_duration = media_data["duration"]
        fps = media_data["fps"]

        available_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(
                start_frame, fps),
            duration=otio.opentime.RationalTime(
                frame_duration, fps)
        )
        # in case old OTIO or video file create `ExternalReference`
        media_reference = otio.schema.ExternalReference(
            target_url=media_path,
            available_range=available_range
        )
        otio_clip.media_reference = media_reference

    def _get_media_source_metadata(self, path):
        """Get all available metadata from file

        Args:
            path (str): media file path string

        Raises:
            AssertionError: ffprobe couldn't read metadata

        Returns:
            dict: media file metadata
        """
        return_data = {}

        try:
            media_data = get_ffprobe_data(
                path, self.log
            )

            # get video stream data
            video_streams = []
            audio_streams = []
            for stream in media_data["streams"]:
                codec_type = stream.get("codec_type")
                if codec_type == "audio":
                    audio_streams.append(stream)

                elif codec_type == "video":
                    video_streams.append(stream)

            if not video_streams:
                raise ValueError(
                    "Could not find video stream in source file."
                )

            video_stream = video_streams[0]
            return_data = {
                "video": True,
                "start_frame": 0,
                "duration": int(video_stream["nb_frames"]),
                "fps": float(
                    convert_ffprobe_fps_value(
                        video_stream["r_frame_rate"]
                    )
                )
            }

            # get audio  streams data
            if audio_streams:
                return_data["audio"] = True

        except Exception as exc:
            raise AssertionError((
                "FFprobe couldn't read information about input file: "
                f"\"{path}\". Error message: {exc}"
            ))

        return return_data

    def _make_product_instance(
        self,
        otio_clip,
        product_type_preset,
        instance_data,
        parenting_data
    ):
        """Making product instance from input preset

        Args:
            otio_clip (otio.Clip): otio clip object
            product_type_preset (dict): single product type preset
            instance_data (dict): instance data
            parenting_data (dict): shot instance parent data

        Returns:
            CreatedInstance: creator instance object
        """
        product_type = product_type_preset["product_type"]
        label = self._make_product_naming(
            product_type_preset,
            instance_data
        )
        instance_data["label"] = label

        # add file extension filter only if it is not shot product type
        if product_type == "shot":
            instance_data["otioClip"] = (
                otio.adapters.write_to_string(otio_clip))
            c_instance = self.create_context.creators[
                "editorial_shot"].create(
                    instance_data)
            parenting_data.update({
                "instance_label": label,
                "instance_id": c_instance.data["instance_id"]
            })
        else:
            # add review family if defined
            instance_data.update({
                "outputFileType": product_type_preset["output_file_type"],
                "parent_instance_id": parenting_data["instance_id"],
                "creator_attributes": {
                    "parent_instance": parenting_data["instance_label"],
                    "add_review_family": product_type_preset.get("review")
                }
            })

            creator_identifier = f"editorial_{product_type}"
            editorial_clip_creator = self.create_context.creators[
                creator_identifier]
            c_instance = editorial_clip_creator.create(
                instance_data)

        return c_instance

    def _make_product_naming(self, product_type_preset, instance_data):
        """Product name maker

        Args:
            product_type_preset (dict): single preset item
            instance_data (dict): instance data

        Returns:
            str: label string
        """
        folder_path = instance_data["creator_attributes"]["folderPath"]

        variant_name = instance_data["variant"]
        product_type = product_type_preset["product_type"]

        # get variant name from preset or from inheritance
        _variant_name = product_type_preset.get("variant") or variant_name

        # product name
        product_name = "{}{}".format(
            product_type, _variant_name.capitalize()
        )
        label = "{} {}".format(
            folder_path,
            product_name
        )

        instance_data.update({
            "label": label,
            "variant": _variant_name,
            "productType": product_type,
            "productName": product_name,
        })

        return label

    def _get_base_instance_data(
        self,
        otio_clip,
        instance_data,
        track_start_frame,
        folder_entity,
    ):
        """Factoring basic set of instance data.

        Args:
            otio_clip (otio.Clip): otio clip object
            instance_data (dict): precreate instance data
            track_start_frame (int): track start frame

        Returns:
            dict: instance data

        """
        parent_folder_path = folder_entity["path"]
        parent_folder_name = parent_folder_path.rsplit("/", 1)[-1]

        # get clip instance properties
        handle_start = instance_data["handle_start"]
        handle_end = instance_data["handle_end"]
        timeline_offset = instance_data["timeline_offset"]
        workfile_start_frame = instance_data["workfile_start_frame"]
        fps = instance_data["fps"]
        variant_name = instance_data["variant"]

        # basic unique folder name
        clip_name = os.path.splitext(otio_clip.name)[0]
        project_entity = ayon_api.get_project(self.project_name)

        shot_name, shot_metadata = self._shot_metadata_solver.generate_data(
            clip_name,
            {
                "anatomy_data": {
                    "project": {
                        "name": self.project_name,
                        "code": project_entity["code"]
                    },
                    "parent": parent_folder_name,
                    "app": self.host_name
                },
                "selected_folder_entity": folder_entity,
                "project_entity": project_entity
            }
        )

        timing_data = self._get_timing_data(
            otio_clip,
            timeline_offset,
            track_start_frame,
            workfile_start_frame
        )

        # create creator attributes
        creator_attributes = {

            "workfile_start_frame": workfile_start_frame,
            "fps": fps,
            "handle_start": int(handle_start),
            "handle_end": int(handle_end)
        }
        # add timing data
        creator_attributes.update(timing_data)

        # create base instance data
        base_instance_data = {
            "shotName": shot_name,
            "variant": variant_name,
            "task": None,
            "newAssetPublishing": True,
            "trackStartFrame": track_start_frame,
            "timelineOffset": timeline_offset,

            # creator_attributes
            "creator_attributes": creator_attributes
        }
        # update base instance data with context data
        # and also update creator attributes with context data
        creator_attributes["folderPath"] = shot_metadata.pop("folderPath")
        base_instance_data["folderPath"] = parent_folder_path

        # add creator attributes to shared instance data
        base_instance_data["creator_attributes"] = creator_attributes
        # add hierarchy shot metadata
        base_instance_data.update(shot_metadata)

        return base_instance_data

    def _get_timing_data(
        self,
        otio_clip,
        timeline_offset,
        track_start_frame,
        workfile_start_frame
    ):
        """Returning available timing data

        Args:
            otio_clip (otio.Clip): otio clip object
            timeline_offset (int): offset value
            track_start_frame (int): starting frame input
            workfile_start_frame (int): start frame for shot's workfiles

        Returns:
            dict: timing metadata
        """
        # frame ranges data
        clip_in = otio_clip.range_in_parent().start_time.value
        clip_in += track_start_frame
        clip_out = otio_clip.range_in_parent().end_time_inclusive().value
        clip_out += track_start_frame

        # add offset in case there is any
        if timeline_offset:
            clip_in += timeline_offset
            clip_out += timeline_offset

        clip_duration = otio_clip.duration().value
        source_in = otio_clip.trimmed_range().start_time.value
        source_out = source_in + clip_duration

        # define starting frame for future shot
        frame_start = (
            clip_in if workfile_start_frame is None
            else workfile_start_frame
        )
        frame_end = frame_start + (clip_duration - 1)

        return {
            "frameStart": int(frame_start),
            "frameEnd": int(frame_end),
            "clipIn": int(clip_in),
            "clipOut": int(clip_out),
            "clipDuration": int(otio_clip.duration().value),
            "sourceIn": int(source_in),
            "sourceOut": int(source_out)
        }

    def _get_allowed_product_type_presets(self, pre_create_data):
        """Filter out allowed product type presets.

        Args:
            pre_create_data (dict): precreate attributes inputs

        Returns:
            list: lit of dict with preset items
        """
        return [
            {"product_type": "shot"},
            *[
                preset
                for preset in self.product_type_presets
                if pre_create_data[preset["product_type"]]
            ]
        ]

    def _validate_clip_for_processing(self, otio_clip):
        """Validate otio clip attributes

        Args:
            otio_clip (otio.Clip): otio clip object

        Returns:
            bool: True if all passing conditions
        """
        if otio_clip.name is None:
            return False

        if isinstance(otio_clip, otio.schema.Gap):
            return False

        # skip all generators like black empty
        if isinstance(
            otio_clip.media_reference,
                otio.schema.GeneratorReference):
            return False

        # Transitions are ignored, because Clips have the full frame
        # range.
        if isinstance(otio_clip, otio.schema.Transition):
            return False

        return True

    def get_pre_create_attr_defs(self):
        """Creating pre-create attributes at creator plugin.

        Returns:
            list: list of attribute object instances
        """
        # Use same attributes as for instance attrobites
        attr_defs = [
            FileDef(
                "sequence_filepath_data",
                folders=False,
                extensions=[
                    ".edl",
                    ".xml",
                    ".aaf",
                    ".fcpxml"
                ],
                allow_sequences=False,
                single_item=False,
                label="Sequence file",
            ),
            FileDef(
                "media_filepaths_data",
                folders=False,
                extensions=[
                    ".mov",
                    ".mp4",
                    ".wav"
                ],
                allow_sequences=False,
                single_item=False,
                label="Media files",
            ),
            # TODO: perhaps better would be timecode and fps input
            NumberDef(
                "timeline_offset",
                default=0,
                label="Timeline offset"
            ),
            UISeparatorDef(),
            UILabelDef("Clip instance attributes"),
            UISeparatorDef()
        ]
        # add variants swithers
        attr_defs.extend(
            BoolDef(item["product_type"], label=item["product_type"])
            for item in self.product_type_presets
        )
        attr_defs.append(UISeparatorDef())

        attr_defs.extend(CLIP_ATTR_DEFS)
        return attr_defs
