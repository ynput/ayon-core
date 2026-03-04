import collections
import hashlib
import os
import tempfile
import uuid
from pathlib import Path

import pyblish
from ayon_core.lib import get_ffmpeg_tool_args, run_subprocess


def get_audio_instances(context):
    """Return only instances which are having audio in families

    Args:
        context (pyblish.context): context of publisher

    Returns:
        list: list of selected instances
    """
    audio_instances = []
    for instance in context:
        if not instance.data.get("parent_instance_id"):
            continue

        product_base_type = instance.data.get("productBaseType")
        if not product_base_type:
            product_base_type = instance.data["productType"]
        if (
            product_base_type == "audio"
            or instance.data.get("reviewAudio")
        ):
            audio_instances.append(instance)
    return audio_instances


def map_instances_by_parent_id(context):
    """Create a mapping of instances by their parent id

    Args:
        context (pyblish.context): context of publisher

    Returns:
        dict: mapping of instances by their parent id
    """
    instances_by_parent_id = collections.defaultdict(list)
    for instance in context:
        parent_instance_id = instance.data.get("parent_instance_id")
        if not parent_instance_id:
            continue
        instances_by_parent_id[parent_instance_id].append(instance)
    return instances_by_parent_id


class CollectParentAudioInstanceAttribute(pyblish.api.ContextPlugin):
    """Collect audio instance attribute"""

    order = pyblish.api.CollectorOrder
    label = "Collect Audio Instance Attribute"

    def process(self, context):

        audio_instances = get_audio_instances(context)

        # no need to continue if no audio instances found
        if not audio_instances:
            return

        # create mapped instances by parent id
        instances_by_parent_id = map_instances_by_parent_id(context)

        # distribute audio related attribute
        for audio_instance in audio_instances:
            parent_instance_id = audio_instance.data["parent_instance_id"]

            for sibl_instance in instances_by_parent_id[parent_instance_id]:
                # exclude the same audio instance
                if sibl_instance.id == audio_instance.id:
                    continue
                self.log.info(
                    "Adding audio to Sibling instance: "
                    f"{sibl_instance.data['label']}"
                )
                sibl_instance.data["audio"] = None


class ExtractOtioAudioTracks(pyblish.api.ContextPlugin):
    """Extract Audio tracks from OTIO timeline.

    Process will merge all found audio tracks into one long .wav file at frist
    stage. Then it will trim it into individual short audio files relative to
    asset length and add it to each marked instance data representation. This
    is influenced by instance data audio attribute """

    order = pyblish.api.ExtractorOrder - 0.44
    label = "Extract OTIO Audio Tracks"

    temp_dir_path = None

    def process(self, context):
        """Convert otio audio track's content to audio representations

        Args:
            context (pyblish.Context): context of publisher
        """
        # split the long audio file to peces devided by isntances
        audio_instances = get_audio_instances(context)

        # no need to continue if no audio instances found
        if not audio_instances:
            return

        self.log.debug("Audio instances: {}".format(len(audio_instances)))

        # get sequence
        otio_timeline = context.data["otioTimeline"]

        # get all audio inputs from otio timeline
        audio_inputs = self.get_audio_track_items(otio_timeline)

        if not audio_inputs:
            return

        # Convert all available audio into single file for trimming
        audio_temp_fpath = self.create_temp_file("timeline_audio_track")

        # create empty audio with longest duration
        empty = self.create_empty(audio_inputs)

        # add empty to list of audio inputs
        audio_inputs.insert(0, empty)

        # create cmd
        self.mix_audio(audio_inputs, audio_temp_fpath)

        # remove empty
        os.remove(empty["mediaPath"])

        # create mapped instances by parent id
        instances_by_parent_id = map_instances_by_parent_id(context)

        # cut instance framerange and add to representations
        self.add_audio_to_instances(
            audio_temp_fpath, audio_instances, instances_by_parent_id)

        # remove full mixed audio file
        os.remove(audio_temp_fpath)

    def add_audio_to_instances(
        self, audio_file, audio_instances, instances_by_parent_id):
        created_files = []
        for audio_instance in audio_instances:
            folder_path = audio_instance.data["folderPath"]
            file_suffix = folder_path.replace("/", "-")

            recycling_file = [f for f in created_files if file_suffix in f]
            audio_clip = audio_instance.data["otioClip"]
            audio_range = audio_clip.range_in_parent()
            duration = audio_range.duration.to_frames()

            # ffmpeg generate new file only if doesn't exists already
            if not recycling_file:
                parent_track = audio_clip.parent()
                parent_track_start = parent_track.range_in_parent().start_time
                relative_start_time = (
                    audio_range.start_time - parent_track_start)
                start_sec = relative_start_time.to_seconds()
                duration_sec = audio_range.duration.to_seconds()

                # shot related audio file
                shot_audio_fpath = self.create_temp_file(file_suffix)

                cmd = get_ffmpeg_tool_args(
                    "ffmpeg",
                    "-ss", str(start_sec),
                    "-t", str(duration_sec),
                    "-i", audio_file,
                    shot_audio_fpath
                )

                # run subprocess
                self.log.debug("Executing: {}".format(" ".join(cmd)))
                run_subprocess(cmd, logger=self.log)

                # add generated audio file to created files for recycling
                if shot_audio_fpath not in created_files:
                    created_files.append(shot_audio_fpath)
            else:
                shot_audio_fpath = recycling_file.pop()

            # audio file needs to be published as representation
            a_product_base_type = audio_instance.data.get("productBaseType")
            if not a_product_base_type:
                a_product_base_type = audio_instance.data["productType"]

            if a_product_base_type == "audio":
                # create empty representation attr
                if "representations" not in audio_instance.data:
                    audio_instance.data["representations"] = []
                # add to representations
                audio_instance.data["representations"].append({
                    "files": os.path.basename(shot_audio_fpath),
                    "name": "wav",
                    "ext": "wav",
                    "stagingDir": os.path.dirname(shot_audio_fpath),
                    "frameStart": 0,
                    "frameEnd": duration
                })

            # audio file needs to be reviewable too
            elif "reviewAudio" in audio_instance.data.keys():
                audio_attr = audio_instance.data.get("audio") or []
                audio_attr.append({
                    "filename": shot_audio_fpath,
                    "offset": 0
                })
                audio_instance.data["audio"] = audio_attr

            # Make sure if the audio instance is having siblink instances
            # which needs audio for reviewable media so it is also added
            # to its instance data
            # Retrieve instance data from parent instance shot instance.
            parent_instance_id = audio_instance.data["parent_instance_id"]
            for sibl_instance in instances_by_parent_id[parent_instance_id]:
                # exclude the same audio instance
                if sibl_instance.id == audio_instance.id:
                    continue
                self.log.info(
                    "Adding audio to Sibling instance: "
                    f"{sibl_instance.data['label']}"
                )
                audio_attr = sibl_instance.data.get("audio") or []
                audio_attr.append({
                    "filename": shot_audio_fpath,
                    "offset": 0
                })
                sibl_instance.data["audio"] = audio_attr

    def get_audio_track_items(self, otio_timeline):
        """Get all audio clips form OTIO audio tracks

        Args:
            otio_timeline (otio.schema.timeline): timeline object

        Returns:
            list: list of audio clip dictionaries
        """
        # Not all hosts can import this module.
        import opentimelineio as otio
        from ayon_core.pipeline.editorial import OTIO_EPSILON

        output = []
        # go trough all audio tracks
        for otio_track in otio_timeline.audio_tracks():
            self.log.debug("_" * 50)
            playhead = 0
            for otio_clip in otio_track:
                self.log.debug(otio_clip)
                if (isinstance(otio_clip, otio.schema.Clip) and
                    not otio_clip.media_reference.is_missing_reference):
                    media_av_start = otio_clip.available_range().start_time
                    clip_start = otio_clip.source_range.start_time
                    fps = clip_start.rate
                    conformed_av_start = media_av_start.rescaled_to(fps)

                    # Avoid rounding issue on media available range.
                    if clip_start.almost_equal(
                        conformed_av_start,
                        OTIO_EPSILON
                    ):
                        conformed_av_start = clip_start

                    # ffmpeg ignores embedded tc
                    start = clip_start - conformed_av_start
                    duration = otio_clip.source_range.duration
                    media_path = otio_clip.media_reference.target_url
                    input = {
                        "mediaPath": media_path,
                        "delayFrame": playhead,
                        "startFrame": start.to_frames(),
                        "durationFrame": duration.to_frames(),
                        "delayMilSec": int(float(playhead / fps) * 1000),
                        "startSec": start.to_seconds(),
                        "durationSec": duration.to_seconds(),
                        "fps": float(fps)
                    }
                    if input not in output:
                        output.append(input)
                        self.log.debug("__ input: {}".format(input))

                playhead += otio_clip.source_range.duration.value

        return output

    def create_empty(self, inputs):
        """Create an empty audio file used as duration placeholder

        Args:
            inputs (list): list of audio clip dictionaries

        Returns:
            dict: audio clip dictionary
        """
        # temp file
        empty_fpath = self.create_temp_file("empty")

        # get all end frames
        end_secs = [(_i["delayFrame"] + _i["durationFrame"]) / _i["fps"]
                    for _i in inputs]
        # get the max of end frames
        max_duration_sec = max(end_secs)

        # create empty cmd
        cmd = get_ffmpeg_tool_args(
            "ffmpeg",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t", str(max_duration_sec),
            empty_fpath
        )

        # generate empty with ffmpeg
        # run subprocess
        self.log.debug("Executing: {}".format(" ".join(cmd)))

        run_subprocess(
            cmd, logger=self.log
        )

        # return dict with output
        return {
            "mediaPath": empty_fpath,
            "delayMilSec": 0,
            "startSec": 0.00,
            "durationSec": max_duration_sec
        }

    def mix_audio(self, audio_inputs, audio_temp_fpath):
        """Creating multiple input cmd string

        Args:
            audio_inputs (list): list of input dicts. Order mater.

        Returns:
            str: the command body
        """

        longest_input = 0
        for audio_input in audio_inputs:
            audio_len = audio_input["durationSec"]
            if audio_len > longest_input:
                longest_input = audio_len

        # create cmd segments
        input_args = []
        filters = []
        tag_names = []
        for index, audio_input in enumerate(audio_inputs):
            input_args.extend([
                "-ss", str(audio_input["startSec"]),
                "-t", str(audio_input["durationSec"]),
                "-i", audio_input["mediaPath"]
            ])

            # Output tag of a filtered audio input
            tag_name = "[r{}]".format(index)
            tag_names.append(tag_name)
            # Delay in audio by delay in item
            filters.append("[{}]adelay={}:all=1{}".format(
                index, audio_input["delayMilSec"], tag_name
            ))

        # Mixing filter
        #   - dropout transition (when audio will get loader) is set to be
        #       higher then any input audio item
        #   - volume is set to number of inputs - each mix adds 1/n volume
        #       where n is input inder (to get more info read ffmpeg docs and
        #       send a giftcard to contributor)
        filters.append(
            (
                "{}amix=inputs={}:duration=first:"
                "dropout_transition={},volume={}[a]"
            ).format(
                "".join(tag_names),
                len(audio_inputs),
                (longest_input * 1000) + 1000,
                len(audio_inputs),
            )
        )

        # Store filters to a file (separated by ',')
        #   - this is to avoid "too long" command issue in ffmpeg
        with tempfile.NamedTemporaryFile(
            delete=False, mode="w", suffix=".txt"
        ) as tmp_file:
            filters_tmp_filepath = tmp_file.name
            tmp_file.write(",".join(filters))

        args = get_ffmpeg_tool_args("ffmpeg")
        args.extend(input_args)
        args.extend([
            "-filter_complex_script", filters_tmp_filepath,
            "-map", "[a]"
        ])
        args.append(audio_temp_fpath)

        # run subprocess
        self.log.debug("Executing: {}".format(args))
        run_subprocess(args, logger=self.log)

        os.remove(filters_tmp_filepath)

    def create_temp_file(self, file_suffix):
        """Create temp wav file

        Args:
            file_suffix (str): name to be used in file name

        Returns:
            str: temp fpath
        """
        extension = ".wav"
        # get 8 characters
        hash = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:8]
        file_name = f"{hash}_{file_suffix}{extension}"

        if not self.temp_dir_path:
            audio_temp_dir_path = tempfile.mkdtemp(prefix="AYON_audio_")
            self.temp_dir_path = Path(audio_temp_dir_path)
            self.temp_dir_path.mkdir(parents=True, exist_ok=True)

        return (self.temp_dir_path / file_name).as_posix()
