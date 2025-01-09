"""Plugins for collecting OTIO frame ranges and related timing information.

This module contains three plugins:
- CollectOtioFrameRanges: Collects basic timeline frame ranges
- CollectOtioSourceRanges: Collects source media frame ranges
- CollectOtioRetimedRanges: Handles retimed clip frame ranges
"""

from pprint import pformat
from typing import Any

import pyblish.api

try:
    import opentimelineio as otio
except ImportError:
    raise RuntimeError("OpenTimelineIO is not installed.")

from ayon_core.pipeline.editorial import (
    get_media_range_with_retimes,
    otio_range_to_frame_range,
    otio_range_with_handles,
)


def validate_otio_clip(instance: Any, logger: Any) -> bool:
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

class CollectOtioFrameRanges(pyblish.api.InstancePlugin):
    """Collect basic timeline frame ranges from OTIO clip.

    This plugin extracts and stores basic timeline frame ranges including
    handles from the OTIO clip.

    Requires:
        otioClip (otio.schema.Clip): OTIO clip object
        workfileFrameStart (int): Starting frame of work file

    Provides:
        frameStart (int): Start frame in timeline
        frameEnd (int): End frame in timeline
        clipIn (int): Clip in point
        clipOut (int): Clip out point
        clipInH (int): Clip in point with handles
        clipOutH (int): Clip out point with handles
    """

    label = "Collect OTIO Frame Ranges"
    order = pyblish.api.CollectorOrder - 0.08
    families = ["shot", "clip"]
    hosts = ["resolve", "hiero", "flame", "traypublisher"]

    def process(self, instance: Any) -> None:
        """Process the instance to collect frame ranges.

        Args:
            instance: The instance to process
        """

        if not validate_otio_clip(instance, self.log):
            return

        otio_clip = instance.data["otioClip"]
        workfile_start = instance.data["workfileFrameStart"]

        # Get timeline ranges
        otio_tl_range = otio_clip.range_in_parent()
        otio_tl_range_handles = otio_range_with_handles(otio_tl_range, instance)

        # Convert to frames
        tl_start, tl_end = otio_range_to_frame_range(otio_tl_range)
        tl_start_h, tl_end_h = otio_range_to_frame_range(otio_tl_range_handles)

        frame_start = workfile_start
        frame_end = frame_start + otio.opentime.to_frames(
            otio_tl_range.duration, otio_tl_range.duration.rate) - 1

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


class CollectOtioSourceRanges(pyblish.api.InstancePlugin):
    """Collect source media frame ranges from OTIO clip.

    This plugin extracts and stores source media frame ranges including
    handles from the OTIO clip.

    Requires:
        otioClip (otio.schema.Clip): OTIO clip object

    Provides:
        sourceStart (int): Source media start frame
        sourceEnd (int): Source media end frame
        sourceStartH (int): Source media start frame with handles
        sourceEndH (int): Source media end frame with handles
    """

    label = "Collect Source OTIO Frame Ranges"
    order = pyblish.api.CollectorOrder - 0.07
    families = ["shot", "clip"]
    hosts = ["hiero", "flame"]

    def process(self, instance: Any) -> None:
        """Process the instance to collect source frame ranges.

        Args:
            instance: The instance to process
        """

        if not validate_otio_clip(instance, self.log):
            return

        otio_clip = instance.data["otioClip"]

        # Get source ranges
        otio_src_range = otio_clip.source_range
        otio_available_range = otio_clip.available_range()
        otio_src_range_handles = otio_range_with_handles(otio_src_range, instance)

        # Get source available start frame
        src_starting_from = otio.opentime.to_frames(
            otio_available_range.start_time,
            otio_available_range.start_time.rate
        )

        # Convert to frames
        src_start, src_end = otio_range_to_frame_range(otio_src_range)
        src_start_h, src_end_h = otio_range_to_frame_range(otio_src_range_handles)

        data = {
            "sourceStart": src_starting_from + src_start,
            "sourceEnd": src_starting_from + src_end - 1,
            "sourceStartH": src_starting_from + src_start_h,
            "sourceEndH": src_starting_from + src_end_h - 1,
        }
        instance.data.update(data)
        self.log.debug(f"Added source ranges: {pformat(data)}")


class CollectOtioRetimedRanges(pyblish.api.InstancePlugin):
    """Update frame ranges for retimed clips.

    This plugin updates the frame end value for retimed clips.

    Requires:
        otioClip (otio.schema.Clip): OTIO clip object
        workfileFrameStart (int): Starting frame of work file
        shotDurationFromSource (Optional[int]): Duration from source if retimed

    Provides:
        frameEnd (int): Updated end frame for retimed clips
    """

    label = "Collect Retimed OTIO Frame Ranges"
    order = pyblish.api.CollectorOrder - 0.06
    families = ["shot", "clip"]
    hosts = ["hiero", "flame"]

    def process(self, instance: Any) -> None:
        """Process the instance to handle retimed clips.

        Args:
            instance: The instance to process
        """
        if not validate_otio_clip(instance, self.log):
            return

        workfile_source_duration = instance.data.get("shotDurationFromSource")
        if not workfile_source_duration:
            self.log.debug("No source duration found, skipping retime handling.")
            return

        otio_clip = instance.data["otioClip"]
        frame_start = instance.data["frameStart"]

        # Handle retimed clip frame range
        retimed_attributes = get_media_range_with_retimes(otio_clip, 0, 0)
        self.log.debug(f"Retimed attributes: {retimed_attributes}")

        media_in = int(retimed_attributes["mediaIn"])
        media_out = int(retimed_attributes["mediaOut"])
        frame_end = frame_start + (media_out - media_in) + 1

        instance.data["frameEnd"] = frame_end
        self.log.debug(f"Updated frameEnd for retimed clip: {frame_end}")
