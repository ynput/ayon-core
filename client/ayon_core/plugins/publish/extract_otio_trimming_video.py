"""
Requires:
    instance -> otioTrimmingRange
    instance -> representations

"""
from __future__ import annotations

import os
import typing

import pyblish.api

from ayon_core.lib import (
    get_ffprobe_data,
    get_ffmpeg_tool_args,
    get_ffmpeg_codec_args,
    run_subprocess,
)
from ayon_core.pipeline import publish

if typing.TYPE_CHECKING:
    from opentimelineio.opentime import TimeRange


class ExtractOTIOTrimmingVideo(publish.Extractor):
    """
    Trimming video file longer then required lenght

    """
    order = pyblish.api.ExtractorOrder
    label = "Extract OTIO trim longer video"
    families = ["otio.trim.video"]

    def process(self, instance):
        repres_to_trim = [
            repre
            for repre in instance.data["representations"]
            if "trim" in repre.get("tags", [])
        ]
        if not repres_to_trim:
            self.log.info(
                "No representation with 'trim' tag found, skipping trimming"
            )
            return

        staging_dir = self.staging_dir(instance)
        otio_trim_range = instance.data["otioTrimmingRange"]
        self.log.debug(f"otio_trim_range: {otio_trim_range}")
        self.log.debug(f"staging_dir: {staging_dir}")

        # get corresponding representation
        for repre in repres_to_trim:
            input_file_path = os.path.normpath(os.path.join(
                repre["stagingDir"], repre["files"]
            ))
            self.log.debug(f"input_file_path: {input_file_path}")

            # trim via ffmpeg
            new_file = self._ffmpeg_trim_seqment(
                staging_dir, input_file_path, otio_trim_range
            )

            # remove tags as we dont need them
            repre.pop("tags")
            repre["stagingDir"] = staging_dir
            repre["files"] = new_file

            self.log.debug(f"Updated representation: {repre}")

    def _ffmpeg_trim_seqment(
        self,
        staging_dir: str,
        input_file_path: str,
        otio_range: TimeRange,
    ) -> str:
        """
        Trim seqment of video file.

        Using ffmpeg to trim video to desired length.

        Args:
            staging_dir (str): Instance staging dir where to store
                trimmed video.
            input_file_path (str): Input path to trim.
            otio_range (TimeRange): Range to trim to.

        Returns:
            str: Filename of the trimmed file.

        """
        # start command list
        command = get_ffmpeg_tool_args("ffmpeg")

        video_path = input_file_path
        sec_start = otio_range.start_time.to_seconds()
        sec_duration = otio_range.duration.to_seconds()

        # form command for rendering gap files
        command.extend([
            "-ss", str(sec_start),
            "-t", str(sec_duration),
            "-i", video_path,
        ])

        ffprobe_data = get_ffprobe_data(input_file_path, logger=self.log)
        video_codec_args = get_ffmpeg_codec_args(ffprobe_data)

        # Trim the video by re-encoding the relevant part of it to
        # the same codec. This is the only way to ensure a precise
        # output duration.
        if video_codec_args:
            command.extend(video_codec_args)

        # Cannot identify video codec, won't be able to re-encode and ensure
        # precise duration. FFmpeg will cut at keyframes.
        # https://video.stackexchange.com/questions/16750/
        # Use '-c copy' which preserve the original video codec.
        else:
            self.log.warning(
                "FFmpeg could not identify the video codec for %s. "
                "Falling back to '-c copy' which may lead to"
                " duration mismatches.",
                input_file_path,
            )
            command.extend(["-c", "copy"])

        # create and append path to destination
        output_path = self._get_ffmpeg_output(staging_dir, input_file_path)
        command.append(output_path)

        # execute
        self.log.debug(f"Executing: {' '.join(command)}")
        output = run_subprocess(
            command, logger=self.log
        )
        self.log.debug(f"Output\n{output}")

        return os.path.basename(output_path)

    def _get_ffmpeg_output(self, staging_dir, file_path):
        """
        Returning ffmpeg output command arguments.

        Arguments:
            staging_dir (str): Instance staging dir where to store
                trimmed video.
            file_path (str): Source file path to trim.

        Returns:
            str: output_path is path

        """
        basename = os.path.basename(file_path)
        name, ext = os.path.splitext(basename)

        output_file = f"{name}_trimmed{ext}"
        # create path to destination
        return os.path.join(staging_dir, output_file)
