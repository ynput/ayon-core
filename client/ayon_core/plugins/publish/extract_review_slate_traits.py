"""Trait-based variant of `extract_review_slate.py`.

Adds slate frame at the start of trait-based review videos tagged
"slate-frame". `ExtractReviewSlate` only looks at
`instance.data["representations"]`, this plugin only looks at
`get_trait_representations(instance)`.

Review outputs pass the ffmpeg command and output definition to this
plugin in the `ReviewOutput` trait. The representation is updated to
the video with slate: its frame range starts one frame earlier and
the `Slate` trait marks the slate frame.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from pprint import pformat
from typing import Optional

import pyblish.api

from ayon_core.lib import (
    get_ffmpeg_codec_args,
    get_ffmpeg_format_args,
    get_ffmpeg_tool_args,
    get_ffprobe_data,
    get_ffprobe_streams,
    path_to_subprocess_arg,
    run_subprocess,
)
from ayon_core.pipeline.publish import (
    PublishError,
    get_trait_representations,
    has_trait_representations,
    set_trait_representations,
)
from ayon_core.pipeline.publish.trait_utils import (
    get_file_paths,
    get_tags,
    is_sequence,
    set_tags,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    FileLocation,
    FrameRanged,
    Representation,
    ReviewOutput,
    Slate,
)
from ayon_core.plugins.publish import extract_review_slate


class ExtractReviewSlateTraits(extract_review_slate.ExtractReviewSlate):
    """Add slate frame at the start of trait-based review videos."""

    label = "Review with Slate frame (Traits)"

    def process(self, instance: pyblish.api.Instance) -> None:
        if not has_trait_representations(instance):
            return

        slates_data = self._get_slates_data(instance)
        if not slates_data:
            return
        self.log.debug(f"_ slates_data: {pformat(slates_data)}")

        representations = get_trait_representations(instance)
        for representation in representations:
            if "slate-frame" not in get_tags(representation):
                continue
            if is_sequence(representation):
                self.log.warning(
                    f"Representation '{representation.name}' is not a video"
                    " file. Slate can't be added."
                )
                continue
            self._add_slate(instance, representation, slates_data)

        # Remove any representations tagged for deletion.
        result = []
        for representation in representations:
            tags = get_tags(representation)
            if "delete" in tags and "need_thumbnail" not in tags:
                self.log.debug(
                    f"Removing representation: {representation.name}"
                )
                continue
            result.append(representation)
        set_trait_representations(instance, result)

    @staticmethod
    def _get_slates_data(
            instance: pyblish.api.Instance) -> Optional[dict[str, str]]:
        """Get slate paths by file name patterns from upstream."""
        slates_data = instance.data.get("slateFrames")
        slate_frame = instance.data.get("slateFrame")
        if not slates_data and slate_frame is not None:
            # make it backward compatible and open for slates generator
            # premium plugin
            slates_data = {"*": slate_frame}
        return slates_data

    def _add_slate(
        self,
        instance: pyblish.api.Instance,
        representation: Representation,
        slates_data: dict[str, str],
    ) -> None:
        """Prepend slate frame to the video of the representation.

        Representation is updated to point to the video with slate.
        """
        input_path = str(get_file_paths(representation)[0])
        input_dir, input_file = os.path.split(input_path)
        self.log.debug(f"__ input_path: {input_path}")

        review_output = None
        if representation.contains_trait(ReviewOutput):
            review_output = representation.get_trait(ReviewOutput)
        source_ffmpeg_cmd = review_output.ffmpeg_cmd if review_output else None
        output_def = (review_output.output_def if review_output else {}) or {}

        streams = get_ffprobe_streams(input_path, self.log)
        slate_path = self._get_slate_path(input_file, slates_data)
        self.log.debug(f"_ slate_path: {slate_path}")
        slate_width, slate_height = self._get_slates_resolution(slate_path)

        (
            input_width,
            input_height,
            input_timecode,
            input_frame_rate,
            input_pixel_aspect,
        ) = self._get_video_metadata(streams)
        pixel_aspect = instance.data.get("pixelAspect", 1)
        if input_pixel_aspect:
            pixel_aspect = input_pixel_aspect

        if input_width is None:
            raise PublishError(
                "FFprobe couldn't read resolution from input file:"
                f" \"{input_path}\""
            )

        (
            audio_codec,
            audio_channels,
            audio_sample_rate,
            audio_channel_layout,
            input_audio,
        ) = self._get_audio_metadata(streams)

        ext = os.path.splitext(input_file)[1]
        output_file = input_file.replace(ext, "") + self.SUFFIX + ext
        output_path = os.path.join(os.path.normpath(input_dir), output_file)
        self.log.debug(f"__ output_path: {output_path}")
        remove_at_end = [input_path]

        input_args = list(output_def.get("input", []))
        input_args.extend([
            "-loop", "1",
            "-i", path_to_subprocess_arg(slate_path),
            "-r", str(input_frame_rate),
            "-frames:v", "1",
        ])

        # add timecode from source to the slate, substract one frame
        offset_timecode = ""
        if input_timecode:
            offset_timecode = self._tc_offset(
                str(input_timecode),
                framerate=instance.data.get("fps"),
                frame_offset=-1
            )
            self.log.debug(f"Slate Timecode: `{offset_timecode}`")

        # Codecs are copied from source for whole input
        format_args, codec_args = self._get_trait_format_codec_args(
            input_path, source_ffmpeg_cmd
        )
        output_args = [*format_args, *codec_args]
        # make sure colors are correct
        output_args.extend([
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
        ])
        output_args.insert(0, self._get_scale_filter_args(
            output_args,
            slate_width,
            slate_height,
            input_width,
            input_height,
            pixel_aspect,
            input_frame_rate,
        ))
        # overrides output file
        output_args.append("-y")

        slate_v_path = slate_path.replace(".png", ext)
        output_args.append(path_to_subprocess_arg(slate_v_path))
        remove_at_end.append(slate_v_path)

        slate_subprocess_cmd = " ".join([
            subprocess.list2cmdline(get_ffmpeg_tool_args("ffmpeg")),
            " ".join(input_args),
            " ".join(output_args),
        ])
        self.log.debug(f"Slate Executing: {slate_subprocess_cmd}")
        run_subprocess(slate_subprocess_cmd, shell=True, logger=self.log)

        # Create slate with silent audio track
        if input_audio:
            slate_silent_path = "_silent".join(os.path.splitext(slate_v_path))
            remove_at_end.append(slate_silent_path)
            self._create_silent_slate(
                slate_v_path,
                slate_silent_path,
                audio_codec,
                audio_channels,
                audio_sample_rate,
                audio_channel_layout,
                input_frame_rate
            )
            # replace slate with silent slate for concat
            slate_v_path = slate_silent_path

        # concat slate and videos together with concat filter
        # this will reencode the output
        if input_audio:
            fmap = [
                "-filter_complex",
                "[0:v] [0:a] [1:v] [1:a] concat=n=2:v=1:a=1 [v] [a]",
                "-map", "[v]",
                "-map", "[a]"
            ]
        else:
            fmap = [
                "-filter_complex",
                "[0:v] [1:v] concat=n=2:v=1:a=0 [v]",
                "-map", "[v]"
            ]
        concat_args = get_ffmpeg_tool_args(
            "ffmpeg",
            "-y",
            "-i", slate_v_path,
            "-i", input_path,
        )
        concat_args.extend(fmap)
        if offset_timecode:
            concat_args.extend(["-timecode", offset_timecode])
        # NOTE: Added because of OP Atom demuxers
        # Add format arguments if there are any
        # - keep format of output
        concat_args.extend(format_args)
        concat_args.extend(codec_args)

        # Use arguments from ffmpeg preset
        if source_ffmpeg_cmd:
            copy_args = (
                "-metadata",
                "-metadata:s:v:0",
                "-b:v",
                "-b:a",
            )
            args = source_ffmpeg_cmd.split(" ")
            for idx, arg in enumerate(args):
                if arg in copy_args:
                    concat_args.append(arg)
                    # assumes arg has one parameter
                    concat_args.append(args[idx + 1])

        concat_args.append(output_path)
        self.log.debug(
            "Executing concat filter: {}".format(" ".join(concat_args))
        )
        run_subprocess(concat_args, logger=self.log)

        self._update_representation(representation, Path(output_path))

        for path in remove_at_end:
            os.remove(path)
            self.log.debug(f"Removed: `{path}`")

    def _get_scale_filter_args(
        self,
        output_args: list[str],
        slate_width: int,
        slate_height: int,
        to_width: int,
        to_height: int,
        pixel_aspect: float,
        input_frame_rate: str,
    ) -> str:
        """Get video filter argument scaling slate to the video resolution.

        Video filters in `output_args` are removed and merged with
        the scaling filter.
        """
        resolution_ratio = (float(slate_width) * pixel_aspect) / slate_height
        delivery_ratio = float(to_width) / float(to_height)
        self.log.debug(f"resolution_ratio: `{resolution_ratio}`")
        self.log.debug(f"delivery_ratio: `{delivery_ratio}`")

        scale_factor_by_height = float(to_height) / slate_height
        scale_factor_by_width = float(to_width) / (slate_width * pixel_aspect)

        # shorten two decimals long float number for testing conditions
        resolution_ratio_test = float(f"{resolution_ratio:0.2f}")
        delivery_ratio_test = float(f"{delivery_ratio:0.2f}")
        if resolution_ratio_test < delivery_ratio_test:
            self.log.debug("lower then delivery")
            width_scale = int(slate_width * scale_factor_by_height)
            width_half_pad = int((to_width - width_scale) / 2)
            height_scale = to_height
            height_half_pad = 0
        else:
            self.log.debug("heigher then delivery")
            width_scale = to_width
            width_half_pad = 0
            height_scale = int(slate_height * scale_factor_by_width)
            height_half_pad = int((to_height - height_scale) / 2)

        scaling_arg = (
            f"scale={width_scale}x{height_scale}:flags=lanczos"
            ":out_color_matrix=bt709"
            f",pad={to_width}:{to_height}:{width_half_pad}"
            f":{height_half_pad}:black"
            ",setsar=1"
            f",fps={input_frame_rate}"
        )
        return self.add_video_filter_args(output_args, scaling_arg)

    def _get_trait_format_codec_args(
        self,
        input_path: str,
        source_ffmpeg_cmd: Optional[str],
    ) -> tuple[list[str], list[str]]:
        """Detect format and codec arguments of the input video."""
        try:
            ffprobe_data = get_ffprobe_data(input_path, self.log)
        except Exception:
            self.log.warning(
                "Could not get codec data from input.",
                exc_info=True
            )
            return [], []

        format_args = get_ffmpeg_format_args(ffprobe_data, source_ffmpeg_cmd)
        codec_args = get_ffmpeg_codec_args(
            ffprobe_data, source_ffmpeg_cmd, logger=self.log
        )
        return format_args, codec_args

    @staticmethod
    def _update_representation(
            representation: Representation, output_path: Path) -> None:
        """Point representation to the video with slate.

        Frame range includes the slate frame added before the first frame.
        """
        file_location = representation.get_trait(FileLocation)
        file_location.file_path = output_path
        # content changed
        file_location.file_size = None
        file_location.file_hash = None

        set_tags(representation, [
            tag for tag in get_tags(representation) if tag != "delete"
        ])
        update_persistence(representation)

        if representation.contains_trait(FrameRanged):
            representation.get_trait(FrameRanged).frame_start -= 1
        if representation.contains_trait(Slate):
            representation.get_trait(Slate).frames += 1
        else:
            representation.add_trait(Slate(frames=1))
