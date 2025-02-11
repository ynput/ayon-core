"""Plugin for collecting OTIO frame ranges and related timing information.

This module contains a unified plugin that handles:
- Basic timeline frame ranges
- Source media frame ranges
- Retimed clip frame ranges
"""

from pprint import pformat

import opentimelineio as otio
import pyblish.api
from ayon_core.pipeline.editorial import (
    get_media_range_with_retimes,
    otio_range_to_frame_range,
    otio_range_with_handles,
)


def validate_otio_clip(instance, logger):
    """Validate if instance has required OTIO clip data.

    Args:
        instance: The instance to validate
        logger: Logger object to use for debug messages

    Returns:
        bool: True if valid, False otherwise
    """
    if not instance.data.get("otioClip"):
        logger.debug("Skipping collect OTIO range - no clip found.")
        return False
    return True


class CollectOtioRanges(pyblish.api.InstancePlugin):
    """Collect all OTIO-related frame ranges and timing information.

    This plugin handles collection of:
    - Basic timeline frame ranges with handles
    - Source media frame ranges with handles
    - Retimed clip frame ranges

    Requires:
        otioClip (otio.schema.Clip): OTIO clip object
        workfileFrameStart (int): Starting frame of work file

    Optional:
        shotDurationFromSource (int): Duration from source if retimed

    Provides:
        frameStart (int): Start frame in timeline
        frameEnd (int): End frame in timeline
        clipIn (int): Clip in point
        clipOut (int): Clip out point
        clipInH (int): Clip in point with handles
        clipOutH (int): Clip out point with handles
        sourceStart (int): Source media start frame
        sourceEnd (int): Source media end frame
        sourceStartH (int): Source media start frame with handles
        sourceEndH (int): Source media end frame with handles
    """

    label = "Collect OTIO Ranges"
    order = pyblish.api.CollectorOrder - 0.08
    families = ["shot", "clip"]

    def process(self, instance):
        """Process the instance to collect all frame ranges.

        Args:
            instance: The instance to process
        """
        if not validate_otio_clip(instance, self.log):
            return

        otio_clip = instance.data["otioClip"]

        # Collect timeline ranges if workfile start frame is available
        if "workfileFrameStart" in instance.data:
            self._collect_timeline_ranges(instance, otio_clip)

        # Traypublisher Simple or Advanced editorial publishing is
        # working with otio clips which are having no available range
        # because they are not having any media references.
        try:
            otio_clip.available_range()
            has_available_range = True
        except otio._otio.CannotComputeAvailableRangeError:
            self.log.info("Clip has no available range")
            has_available_range = False

        # Collect source ranges if clip has available range
        if has_available_range:
            self._collect_source_ranges(instance, otio_clip)

        # Handle retimed ranges if source duration is available
        if "shotDurationFromSource" in instance.data:
            self._collect_retimed_ranges(instance, otio_clip)

    def _collect_timeline_ranges(self, instance, otio_clip):
        """Collect basic timeline frame ranges."""
        workfile_start = instance.data["workfileFrameStart"]

        # Get timeline ranges
        otio_tl_range = otio_clip.range_in_parent()
        otio_tl_range_handles = otio_range_with_handles(otio_tl_range, instance)

        # Convert to frames
        tl_start, tl_end = otio_range_to_frame_range(otio_tl_range)
        tl_start_h, tl_end_h = otio_range_to_frame_range(otio_tl_range_handles)

        frame_start = workfile_start
        frame_end = frame_start + otio_tl_range.duration.to_frames() - 1

        data = {
            "frameStart": frame_start,
            "frameEnd": frame_end,
            "clipIn": tl_start,
            "clipOut": tl_end - 1,
            "clipInH": tl_start_h,
            "clipOutH": tl_end_h - 1,
        }
        instance.data.update(data)
        self.log.debug(f"Added frame ranges: {pformat(data)}")

    def _collect_source_ranges(self, instance, otio_clip):
        """Collect source media frame ranges."""
        # Get source ranges
        otio_src_range = otio_clip.source_range
        otio_available_range = otio_clip.available_range()

        # Backward-compatibility for Hiero OTIO exporter.
        # NTSC compatibility might introduce floating rates, when these are
        # not exactly the same (23.976 vs 23.976024627685547)
        # this will cause precision issue in computation.
        # Currently round to 2 decimals for comparison,
        # but this should always rescale after that.
        rounded_av_rate = round(otio_available_range.start_time.rate, 2)
        rounded_src_rate = round(otio_src_range.start_time.rate, 2)
        if rounded_av_rate != rounded_src_rate:
            conformed_src_in = otio_src_range.start_time.rescaled_to(
                otio_available_range.start_time.rate
            )
            conformed_src_duration = otio_src_range.duration.rescaled_to(
                otio_available_range.duration.rate
            )
            conformed_source_range = otio.opentime.TimeRange(
                start_time=conformed_src_in,
                duration=conformed_src_duration
            )
        else:
            conformed_source_range = otio_src_range

        source_start = conformed_source_range.start_time
        source_end = source_start + conformed_source_range.duration
        handle_start = otio.opentime.RationalTime(
            instance.data.get("handleStart", 0),
            source_start.rate
        )
        handle_end = otio.opentime.RationalTime(
            instance.data.get("handleEnd", 0),
            source_start.rate
        )
        source_start_h = source_start - handle_start
        source_end_h = source_end + handle_end
        data = {
            "sourceStart": source_start.to_frames(),
            "sourceEnd": source_end.to_frames() - 1,
            "sourceStartH": source_start_h.to_frames(),
            "sourceEndH": source_end_h.to_frames() - 1,
        }
        instance.data.update(data)
        self.log.debug(f"Added source ranges: {pformat(data)}")

    def _collect_retimed_ranges(self, instance, otio_clip):
        """Handle retimed clip frame ranges."""
        retimed_attributes = get_media_range_with_retimes(otio_clip, 0, 0)
        self.log.debug(f"Retimed attributes: {retimed_attributes}")

        frame_start = instance.data["frameStart"]
        media_in = int(retimed_attributes["mediaIn"])
        media_out = int(retimed_attributes["mediaOut"])
        frame_end = frame_start + (media_out - media_in)

        data = {
            "frameStart": frame_start,
            "frameEnd": frame_end,
            "sourceStart": media_in,
            "sourceEnd": media_out,
            "sourceStartH": media_in - int(retimed_attributes["handleStart"]),
            "sourceEndH": media_out + int(retimed_attributes["handleEnd"]),
        }

        instance.data.update(data)
        self.log.debug(f"Updated retimed values: {data}")
