"""
Requires:
    instance -> handleStart
    instance -> handleEnd
    instance -> otioClip
    instance -> otioReviewClips

Optional:
    instance -> workfileFrameStart
    instance -> resolutionWidth
    instance -> resolutionHeight

Provides:
    instance -> otioReviewClips
"""

import os

import clique
from pyblish import api

from ayon_core.lib import (
    get_ffmpeg_tool_args,
    run_subprocess,
)
from ayon_core.pipeline import publish


class ExtractOTIOReview(
    publish.Extractor,
    publish.ColormanagedPyblishPluginMixin
):
    """
    Extract OTIO timeline into one concuted image sequence file.

    The `otioReviewClip` is holding trimmed range of clips relative to
    the `otioClip`. Handles are added during looping by available list
    of Gap and clips in the track. Handle start (head) is added before
    first Gap or Clip and Handle end (tail) is added at the end of last
    Clip or Gap. In case there is missing source material after the
    handles addition Gap will be added. At the end all Gaps are converted
    to black frames and available material is converted to image sequence
    frames. At the end representation is created and added to the instance.

    At the moment only image sequence output is supported

    """

    order = api.ExtractorOrder - 0.45
    label = "Extract OTIO review"
    families = ["review"]
    hosts = ["resolve", "hiero", "flame"]

    # plugin default attributes
    to_width = 1280
    to_height = 720
    output_ext = ".jpg"

    def process(self, instance):
        # Not all hosts can import these modules.
        import opentimelineio as otio
        from ayon_core.pipeline.editorial import (
            make_sequence_collection,
            remap_range_on_file_sequence,
            is_clip_from_media_sequence
        )

        # TODO refactor from using instance variable
        self.temp_file_head = self._get_folder_name_based_prefix(instance)

        # TODO: convert resulting image sequence to mp4

        # get otio clip and other time info from instance clip
        otio_review_clips = instance.data.get("otioReviewClips")

        if otio_review_clips is None:
            self.log.info(f"Instance `{instance}` has no otioReviewClips")
            return

        # TODO: what if handles are different in `versionData`?
        handle_start = instance.data["handleStart"]
        handle_end = instance.data["handleEnd"]

        # add plugin wide attributes
        self.representation_files = []
        self.used_frames = []
        self.workfile_start = int(instance.data.get(
            "workfileFrameStart", 1001)) - handle_start
        # NOTE: padding has to be converted from
        #       end frame since start could be lower then 1000
        self.padding = len(str(instance.data.get("frameEnd", 1001)))
        self.used_frames.append(self.workfile_start)
        self.to_width = instance.data.get(
            "resolutionWidth") or self.to_width
        self.to_height = instance.data.get(
            "resolutionHeight") or self.to_height

        # skip instance if no reviewable data available
        if (
            not isinstance(otio_review_clips[0], otio.schema.Clip)
            and len(otio_review_clips) == 1
        ):
            self.log.warning(
                "Instance `{}` has nothing to process".format(instance))
            return
        else:
            self.staging_dir = self.staging_dir(instance)
            if not instance.data.get("representations"):
                instance.data["representations"] = list()

        # loop available clips in otio track
        for index, r_otio_cl in enumerate(otio_review_clips):
            # QUESTION: what if transition on clip?

            # Clip: compute process range from available media range.
            src_range = r_otio_cl.source_range
            if isinstance(r_otio_cl, otio.schema.Clip):
                # check if resolution is the same as source
                media_ref = r_otio_cl.media_reference
                media_metadata = media_ref.metadata

                # get from media reference metadata source
                # TODO 'openpype' prefix should be removed (added 24/09/03)
                # NOTE it looks like it is set only in hiero integration
                res_data = {"width": self.to_width, "height": self.to_height}
                for key in res_data:
                    for meta_prefix in ("ayon.source.", "openpype.source."):
                        meta_key = f"{meta_prefix}.{key}"
                        value = media_metadata.get(meta_key)
                        if value is not None:
                            res_data[key] = value
                            break

                self.to_width, self.to_height = (
                    res_data["width"], res_data["height"]
                )
                self.log.debug(
                    "> self.to_width x self.to_height:"
                    f" {self.to_width} x {self.to_height}"
                )

                available_range = r_otio_cl.available_range()
                available_range_start_frame = (
                    available_range.start_time.to_frames()
                )
                processing_range = None
                self.actual_fps = available_range.duration.rate
                start = src_range.start_time.rescaled_to(self.actual_fps)
                duration = src_range.duration.rescaled_to(self.actual_fps)
                src_frame_start = src_range.start_time.to_frames()

                # Temporary.
                # Some AYON custom OTIO exporter were implemented with
                # relative source range for image sequence. Following code
                # maintain backward-compatibility by adjusting available range
                # while we are updating those.
                if (
                    is_clip_from_media_sequence(r_otio_cl)
                    and available_range_start_frame == media_ref.start_frame
                    and src_frame_start < media_ref.start_frame
                ):
                    available_range = otio.opentime.TimeRange(
                        otio.opentime.RationalTime(0, rate=self.actual_fps),
                        available_range.duration,
                    )

            # Gap: no media, generate range based on source range
            else:
                available_range = processing_range = None
                self.actual_fps = src_range.duration.rate
                start = src_range.start_time
                duration = src_range.duration

            # Create handle offsets.
            clip_handle_start = otio.opentime.RationalTime(
                handle_start,
                rate=self.actual_fps,
            )
            clip_handle_end = otio.opentime.RationalTime(
                handle_end,
                rate=self.actual_fps,
            )

            # reframing handles conditions
            if (len(otio_review_clips) > 1) and (index == 0):
                # more clips | first clip reframing with handle
                start -= clip_handle_start
                duration += clip_handle_start
            elif len(otio_review_clips) > 1 \
                        and (index == len(otio_review_clips) - 1):
                # more clips | last clip reframing with handle
                duration += clip_handle_end
            elif len(otio_review_clips) == 1:
                # one clip | add both handles
                start -= clip_handle_start
                duration += (clip_handle_start + clip_handle_end)

            if available_range:
                processing_range = self._trim_available_range(
                    available_range, start, duration)

            # process all track items of the track
            if isinstance(r_otio_cl, otio.schema.Clip):
                # process Clip
                media_ref = r_otio_cl.media_reference
                metadata = media_ref.metadata
                is_sequence = is_clip_from_media_sequence(r_otio_cl)

                # File sequence way
                if is_sequence:
                    # Remap processing range to input file sequence.
                    processing_range_as_frames = (
                        processing_range.start_time.to_frames(),
                        processing_range.end_time_inclusive().to_frames()
                    )
                    first, last = remap_range_on_file_sequence(
                        r_otio_cl,
                        processing_range_as_frames,
                    )
                    input_fps = processing_range.start_time.rate

                    if hasattr(media_ref, "target_url_base"):
                        dirname = media_ref.target_url_base
                        head = media_ref.name_prefix
                        tail = media_ref.name_suffix
                        collection = clique.Collection(
                            head=head,
                            tail=tail,
                            padding=media_ref.frame_zero_padding
                        )
                        collection.indexes.update(
                            [i for i in range(first, (last + 1))])
                        # render segment
                        self._render_segment(
                            sequence=[dirname, collection, input_fps])
                        # generate used frames
                        self._generate_used_frames(
                            len(collection.indexes))
                    else:
                        # in case it is file sequence but not new OTIO schema
                        # `ImageSequenceReference`
                        path = media_ref.target_url
                        collection_data = make_sequence_collection(
                            path, processing_range, metadata)
                        dir_path, collection = collection_data

                        # render segment
                        self._render_segment(
                            sequence=[dir_path, collection, input_fps])
                        # generate used frames
                        self._generate_used_frames(
                            len(collection.indexes))

                # Single video way.
                # Extraction via FFmpeg.
                else:
                    path = media_ref.target_url
                    # Set extract range from 0 (FFmpeg ignores
                    #   embedded timecode).
                    extract_range = otio.opentime.TimeRange(
                        otio.opentime.RationalTime(
                            (
                                processing_range.start_time.value
                                - available_range.start_time.value
                            ),
                            rate=available_range.start_time.rate,
                        ),
                        duration=processing_range.duration,
                    )
                    # render video file to sequence
                    self._render_segment(
                        video=[path, extract_range])
                    # generate used frames
                    self._generate_used_frames(
                        processing_range.duration.value)

            # QUESTION: what if nested track composition is in place?
            else:
                # at last process a Gap
                self._render_segment(gap=duration.to_frames())
                # generate used frames
                self._generate_used_frames(duration.to_frames())

        # creating and registering representation
        representation = self._create_representation(start, duration)

        # add colorspace data to representation
        if colorspace := instance.data.get("reviewColorspace"):
            self.set_representation_colorspace(
                representation, instance.context, colorspace
            )

        instance.data["representations"].append(representation)
        self.log.info("Adding representation: {}".format(representation))

    def _create_representation(self, start, duration):
        """
        Creating representation data.

        Args:
            start (int): start frame
            duration (int): duration frames

        Returns:
            dict: representation data
        """

        end = start + duration

        # create default representation data
        representation_data = {
            "frameStart": start,
            "frameEnd": end,
            "stagingDir": self.staging_dir,
            "tags": ["review", "delete"]
        }

        collection = clique.Collection(
            self.temp_file_head,
            tail=self.output_ext,
            padding=self.padding,
            indexes=set(self.used_frames)
        )
        start = min(collection.indexes)
        end = max(collection.indexes)

        files = [f for f in collection]
        ext = collection.format("{tail}")
        representation_data.update({
            "name": ext[1:],
            "ext": ext[1:],
            "files": files,
            "frameStart": start,
            "frameEnd": end,
        })
        return representation_data

    def _trim_available_range(self, avl_range, start, duration):
        """
        Trim available media range to source range.

        If missing media range is detected it will convert it into
        black frames gaps.

        Args:
            avl_range (otio.time.TimeRange): media available time range
            start (otio.time.RationalTime): start
            duration (otio.time.RationalTime): duration

        Returns:
            otio.time.TimeRange: trimmed available range
        """
        # Not all hosts can import these modules.
        import opentimelineio as otio
        from ayon_core.pipeline.editorial import (
            trim_media_range,
        )

        def _round_to_frame(rational_time):
            """ Handle rounding duration to frame.
            """
            # OpentimelineIO >= 0.16.0
            try:
                return rational_time.round().to_frames()

            # OpentimelineIO < 0.16.0
            except AttributeError:
                return otio.opentime.RationalTime(
                    round(rational_time.value),
                    rate=rational_time.rate,
                ).to_frames()

        avl_start = avl_range.start_time

        # An additional gap is required before the available
        # range to conform source start point and head handles.
        if start < avl_start:
            gap_duration = avl_start - start
            start = avl_start
            duration -= gap_duration
            gap_duration = _round_to_frame(gap_duration)

            # create gap data to disk
            self._render_segment(gap=gap_duration)
            # generate used frames
            self._generate_used_frames(gap_duration)

        # An additional gap is required after the available
        # range to conform to source end point + tail handles
        # (media duration is shorter then clip requirement).
        end_point = start + duration
        avl_end_point = avl_range.end_time_exclusive()
        if end_point > avl_end_point:
            gap_duration = end_point - avl_end_point
            duration -= gap_duration
            gap_duration = _round_to_frame(gap_duration)

            # create gap data to disk
            self._render_segment(
                gap=gap_duration,
                end_offset=duration.to_frames()
            )
            # generate used frames
            self._generate_used_frames(
                gap_duration,
                end_offset=duration.to_frames()
            )

        # return correct trimmed range
        return trim_media_range(
            avl_range,
            otio.opentime.TimeRange(
                start,
                duration
            )
        )

    def _render_segment(self, sequence=None,
                        video=None, gap=None, end_offset=None):
        """
        Render segment into image sequence frames.

        Using ffmpeg to convert compatible video and image source
        to defined image sequence format.

        Args:
            sequence (list): input dir path string, collection object,
                fps in list.
            video (list)[optional]: video_path string, otio_range in list
            gap (int)[optional]: gap duration
            end_offset (int)[optional]: offset gap frame start in frames

        Returns:
            otio.time.TimeRange: trimmed available range
        """
        # Not all hosts can import this module.
        from ayon_core.pipeline.editorial import frames_to_seconds

        # create path  and frame start to destination
        output_path, out_frame_start = self._get_ffmpeg_output()

        if end_offset:
            out_frame_start += end_offset

        # start command list
        command = get_ffmpeg_tool_args("ffmpeg")

        input_extension = None
        if sequence:
            input_dir, collection, sequence_fps = sequence
            in_frame_start = min(collection.indexes)

            # converting image sequence to image sequence
            input_file = collection.format("{head}{padding}{tail}")
            input_path = os.path.join(input_dir, input_file)
            input_extension = os.path.splitext(input_path)[-1]

            """
            Form Command for Rendering Sequence Files

            To explicitly set the input frame range and preserve the frame
            range, avoid silent dropped frames caused by input mismatch
            with FFmpeg's default rate of 25.0 fps. For more info,
            refer to the FFmpeg image2 demuxer.

            Implicit:
                - Input: 100 frames (24fps from metadata)
                - Demuxer: video 25fps
                - Output: 98 frames, dropped 2

            Explicit with "-framerate":
                - Input: 100 frames (24fps from metadata)
                - Demuxer: video 24fps
                - Output: 100 frames, no dropped frames
            """

            command.extend([
                "-start_number", str(in_frame_start),
                "-framerate", str(sequence_fps),
                "-i", input_path
            ])

        elif video:
            video_path, otio_range = video
            frame_start = otio_range.start_time.value
            input_fps = otio_range.start_time.rate
            frame_duration = otio_range.duration.value
            sec_start = frames_to_seconds(frame_start, input_fps)
            sec_duration = frames_to_seconds(
                frame_duration, input_fps
            )
            input_extension = os.path.splitext(video_path)[-1]

            # form command for rendering gap files
            command.extend([
                "-ss", str(sec_start),
                "-t", str(sec_duration),
                "-i", video_path
            ])

        elif gap:
            sec_duration = frames_to_seconds(gap, self.actual_fps)

            # form command for rendering gap files
            command.extend([
                "-t", str(sec_duration),
                "-r", str(self.actual_fps),
                "-f", "lavfi",
                "-i", "color=c=black:s={}x{}".format(
                    self.to_width, self.to_height
                ),
                "-tune", "stillimage"
            ])

        # add output attributes
        command.extend([
            "-start_number", str(out_frame_start)
        ])

        # add copying if extensions are matching
        if (
            input_extension
            and self.output_ext == input_extension
        ):
            command.extend([
                "-c", "copy"
            ])

        # add output path at the end
        command.append(output_path)

        # execute
        self.log.debug("Executing: {}".format(" ".join(command)))
        output = run_subprocess(
            command, logger=self.log
        )
        self.log.debug("Output: {}".format(output))

    def _generate_used_frames(self, duration, end_offset=None):
        """
        Generating used frames into plugin argument `used_frames`.

        The argument `used_frames` is used for checking next available
        frame to start with during rendering sequence segments.

        Args:
            duration (int): duration of frames needed to be generated
            end_offset (int)[optional]: in case frames need to be offseted

        """

        padding = "{{:0{}d}}".format(self.padding)

        if end_offset:
            new_frames = list()
            start_frame = self.used_frames[-1]
            for index in range(end_offset,
                               (int(end_offset + duration))):
                seq_number = padding.format(start_frame + index)
                self.log.debug(
                    "index: `{}` | seq_number: `{}`".format(index, seq_number))
                new_frames.append(int(seq_number))
            new_frames += self.used_frames
            self.used_frames = new_frames
        else:
            for _i in range(1, (int(duration) + 1)):
                if self.used_frames[-1] == self.workfile_start:
                    seq_number = padding.format(self.used_frames[-1])
                    self.workfile_start -= 1
                else:
                    seq_number = padding.format(self.used_frames[-1] + 1)
                    self.used_frames.append(int(seq_number))

    def _get_ffmpeg_output(self):
        """
        Returning ffmpeg output command arguments.

        Returns:
            str: output_path is path for image sequence output
            int: out_frame_start is starting sequence frame

        """
        output_file = "{}{}{}".format(
            self.temp_file_head,
            "%0{}d".format(self.padding),
            self.output_ext
        )
        # create path to destination
        output_path = os.path.join(self.staging_dir, output_file)

        # generate frame start
        out_frame_start = self.used_frames[-1] + 1
        if self.used_frames[-1] == self.workfile_start:
            out_frame_start = self.used_frames[-1]

        return output_path, out_frame_start

    def _get_folder_name_based_prefix(self, instance):
        """Creates 'unique' human readable file prefix to differentiate.

        Multiple instances might share same temp folder, but each instance
        would be differentiated by asset, eg. folder name.

        It ix expected that there won't be multiple instances for same asset.
        """
        folder_path = instance.data["folderPath"]
        folder_name = folder_path.split("/")[-1]
        folder_path = folder_path.replace("/", "_").lstrip("_")

        file_prefix = f"{folder_path}_{folder_name}."
        self.log.debug(f"file_prefix::{file_prefix}")

        return file_prefix
