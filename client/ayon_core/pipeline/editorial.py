import os
import re
import clique

import opentimelineio as otio
from opentimelineio import opentime as _ot


def otio_range_to_frame_range(otio_range):
    start = _ot.to_frames(
        otio_range.start_time, otio_range.start_time.rate)
    end = start + _ot.to_frames(
        otio_range.duration, otio_range.duration.rate)
    return start, end


def otio_range_with_handles(otio_range, instance):
    handle_start = instance.data["handleStart"]
    handle_end = instance.data["handleEnd"]
    handles_duration = handle_start + handle_end
    fps = float(otio_range.start_time.rate)
    start = _ot.to_frames(otio_range.start_time, fps)
    duration = _ot.to_frames(otio_range.duration, fps)

    return _ot.TimeRange(
        start_time=_ot.RationalTime((start - handle_start), fps),
        duration=_ot.RationalTime((duration + handles_duration), fps)
    )


def is_overlapping_otio_ranges(test_otio_range, main_otio_range, strict=False):
    test_start, test_end = otio_range_to_frame_range(test_otio_range)
    main_start, main_end = otio_range_to_frame_range(main_otio_range)
    covering_exp = bool(
        (test_start <= main_start) and (test_end >= main_end)
    )
    inside_exp = bool(
        (test_start >= main_start) and (test_end <= main_end)
    )
    overlaying_right_exp = bool(
        (test_start <= main_end) and (test_end >= main_end)
    )
    overlaying_left_exp = bool(
        (test_end >= main_start) and (test_start <= main_start)
    )

    if not strict:
        return any((
            covering_exp,
            inside_exp,
            overlaying_right_exp,
            overlaying_left_exp
        ))
    else:
        return covering_exp


def convert_to_padded_path(path, padding):
    """
    Return correct padding in sequence string

    Args:
        path (str): path url or simple file name
        padding (int): number of padding

    Returns:
        type: string with reformatted path

    Example:
        convert_to_padded_path("plate.%d.exr") > plate.%04d.exr

    """
    if "%d" in path:
        path = re.sub("%d", "%0{padding}d".format(padding=padding), path)
    return path


def trim_media_range(media_range, source_range):
    """
    Trim input media range with clip source range.

    Args:
        media_range (otio._ot._ot.TimeRange): available range of media
        source_range (otio._ot._ot.TimeRange): clip required range

    Returns:
        otio._ot._ot.TimeRange: trimmed media range

    """
    rw_media_start = _ot.RationalTime(
        source_range.start_time.value,
        media_range.start_time.rate
    )
    rw_media_duration = _ot.RationalTime(
        source_range.duration.value,
        media_range.duration.rate
    )
    return _ot.TimeRange(
        rw_media_start, rw_media_duration)


def range_from_frames(start, duration, fps):
    """
    Returns otio time range.

    Args:
        start (int): frame start
        duration (int): frame duration
        fps (float): frame range

    Returns:
        otio._ot._ot.TimeRange: created range

    """
    return _ot.TimeRange(
        _ot.RationalTime(start, fps),
        _ot.RationalTime(duration, fps)
    )


def frames_to_seconds(frames, framerate):
    """
    Returning seconds.

    Args:
        frames (int): frame
        framerate (float): frame rate

    Returns:
        float: second value
    """

    rt = _ot.from_frames(frames, framerate)
    return _ot.to_seconds(rt)


def frames_to_timecode(frames, framerate):
    rt = _ot.from_frames(frames, framerate)
    return _ot.to_timecode(rt)


def make_sequence_collection(path, otio_range, metadata):
    """
    Make collection from path otio range and otio metadata.

    Args:
        path (str): path to image sequence with `%d`
        otio_range (otio._ot._ot.TimeRange): range to be used
        metadata (dict): data where padding value can be found

    Returns:
        list: dir_path (str): path to sequence, collection object

    """
    if "%" not in path:
        return None
    file_name = os.path.basename(path)
    dir_path = os.path.dirname(path)
    head = file_name.split("%")[0]
    tail = os.path.splitext(file_name)[-1]
    first, last = otio_range_to_frame_range(otio_range)
    collection = clique.Collection(
        head=head, tail=tail, padding=metadata["padding"])
    collection.indexes.update([i for i in range(first, last)])
    return dir_path, collection


def _sequence_resize(source, length):
    step = float(len(source) - 1) / (length - 1)
    for i in range(length):
        low, ratio = divmod(i * step, 1)
        high = low + 1 if ratio > 0 else low
        yield (1 - ratio) * source[int(low)] + ratio * source[int(high)]


def is_clip_from_media_sequence(otio_clip):
    """
    Args:
        otio_clip (otio.schema.Clip): The OTIO clip to check.

    Returns:
        bool. Is the provided clip from an input media sequence ?
    """
    media_ref = otio_clip.media_reference
    metadata = media_ref.metadata

    # OpenTimelineIO 0.13 and newer
    is_input_sequence = (
        hasattr(otio.schema, "ImageSequenceReference") and
        isinstance(media_ref, otio.schema.ImageSequenceReference)
    )

    # OpenTimelineIO 0.12 and older
    is_input_sequence_legacy = bool(metadata.get("padding"))

    return is_input_sequence or is_input_sequence_legacy


def remap_range_on_file_sequence(otio_clip, in_out_range):
    """
    Args:
        otio_clip (otio.schema.Clip): The OTIO clip to check.
        in_out_range (tuple[float, float]): The in-out range to remap.

    Returns:
        tuple(int, int): The remapped range as discrete frame number.

    Raises:
        ValueError. When the otio_clip or provided range is invalid.
    """
    if not is_clip_from_media_sequence(otio_clip):
        raise ValueError(f"Cannot map on non-file sequence clip {otio_clip}.")

    try:
        media_in_trimmed, media_out_trimmed = in_out_range

    except ValueError as error:
        raise ValueError("Invalid in_out_range provided.") from error

    media_ref = otio_clip.media_reference
    available_range = otio_clip.available_range()
    source_range = otio_clip.source_range
    available_range_rate = available_range.start_time.rate
    media_in = available_range.start_time.value
    available_range_start_frame = (
        available_range.start_time.to_frames()
    )

    # Temporary.
    # Some AYON custom OTIO exporter were implemented with relative
    # source range for image sequence. Following code maintain
    # backward-compatibility by adjusting media_in
    # while we are updating those.
    if (
        is_clip_from_media_sequence(otio_clip)
        and available_range_start_frame == media_ref.start_frame
        and source_range.start_time.to_frames() < media_ref.start_frame
    ):
        media_in = 0

    frame_in = otio.opentime.RationalTime.from_frames(
        media_in_trimmed - media_in + media_ref.start_frame,
        rate=available_range_rate,
    ).to_frames()
    frame_out = otio.opentime.RationalTime.from_frames(
        media_out_trimmed - media_in + media_ref.start_frame,
        rate=available_range_rate,
    ).to_frames()

    return frame_in, frame_out


def get_media_range_with_retimes(otio_clip, handle_start, handle_end):
    source_range = otio_clip.source_range
    available_range = otio_clip.available_range()
    available_range_rate = available_range.start_time.rate

    # If media source is an image sequence, returned
    # mediaIn/mediaOut have to correspond
    # to frame numbers from source sequence.
    media_ref = otio_clip.media_reference
    is_input_sequence = is_clip_from_media_sequence(otio_clip)

    # Temporary.
    # Some AYON custom OTIO exporter were implemented with relative
    # source range for image sequence. Following code maintain
    # backward-compatibility by adjusting available range
    # while we are updating those.
    if (
        is_input_sequence
        and available_range.start_time.to_frames() == media_ref.start_frame
        and source_range.start_time.to_frames() < media_ref.start_frame
    ):
        available_range = _ot.TimeRange(
            _ot.RationalTime(0, rate=available_range_rate),
            available_range.duration,
        )

    # Conform source range bounds to available range rate
    # .e.g. embedded TC of (3600 sec/ 1h), duration 100 frames
    #
    # available  |----------------------------------------|  24fps
    #           86400                                86500
    #
    #
    #                90010                90060
    # src        |-----|______duration 2s___|----|        25fps
    #           90000
    #
    #
    #                86409.6                  86466.8
    # conformed  |-------|_____duration _2.38s____|-------|  24fps
    #           86400
    #
    # Note that 24fps is slower than 25fps hence extended duration
    # to preserve media range

    # Compute new source range based on available rate.

    # Backward-compatibility for Hiero OTIO exporter.
    # NTSC compatibility might introduce floating rates, when these are
    # not exactly the same (23.976 vs 23.976024627685547)
    # this will cause precision issue in computation.
    # Currently round to 2 decimals for comparison,
    # but this should always rescale after that.
    rounded_av_rate = round(available_range_rate, 2)
    rounded_src_rate = round(source_range.start_time.rate, 2)
    if rounded_av_rate != rounded_src_rate:
        conformed_src_in = source_range.start_time.rescaled_to(
            available_range_rate
        )
        conformed_src_duration = source_range.duration.rescaled_to(
            available_range_rate
        )
        conformed_source_range = otio.opentime.TimeRange(
            start_time=conformed_src_in,
            duration=conformed_src_duration
        )

    else:
        conformed_source_range = source_range

    # modifiers
    time_scalar = 1.
    offset_in = 0
    offset_out = 0
    time_warp_nodes = []

    # Check for speed effects and adjust playback speed accordingly
    for effect in otio_clip.effects:
        if isinstance(effect, otio.schema.LinearTimeWarp):
            time_scalar = effect.time_scalar

        elif isinstance(effect, otio.schema.FreezeFrame):
            # For freeze frame, playback speed must be set after range
            time_scalar = 0.

        elif isinstance(effect, otio.schema.TimeEffect):
            # For freeze frame, playback speed must be set after range
            name = effect.name
            effect_name = effect.effect_name
            if "TimeWarp" not in effect_name:
                continue
            metadata = effect.metadata
            lookup = metadata.get("lookup")
            if not lookup:
                continue

            # time warp node
            tw_node = {
                "Class": "TimeWarp",
                "name": name
            }
            tw_node.update(metadata)
            tw_node["lookup"] = list(lookup)

            # get first and last frame offsets
            offset_in += lookup[0]
            offset_out += lookup[-1]

            # add to timewarp nodes
            time_warp_nodes.append(tw_node)

    # multiply by time scalar
    offset_in *= time_scalar
    offset_out *= time_scalar

    # scale handles
    handle_start *= abs(time_scalar)
    handle_end *= abs(time_scalar)

    # flip offset and handles if reversed speed
    if time_scalar < 0:
        offset_in, offset_out = offset_out, offset_in
        handle_start, handle_end = handle_end, handle_start

    # compute retimed range
    media_in_trimmed = conformed_source_range.start_time.value + offset_in
    media_out_trimmed = media_in_trimmed + (
        (
            conformed_source_range.duration.value
            * abs(time_scalar)
            + offset_out
        ) - 1
    )

    media_in = available_range.start_time.value
    media_out = available_range.end_time_inclusive().value

    # If media source is an image sequence, returned
    # mediaIn/mediaOut have to correspond
    # to frame numbers from source sequence.
    if is_input_sequence:
        # preserve discrete frame numbers
        media_in_trimmed, media_out_trimmed = remap_range_on_file_sequence(
            otio_clip,
            (media_in_trimmed, media_out_trimmed)
        )
        media_in = media_ref.start_frame
        media_out = media_in + available_range.duration.to_frames() - 1

    # adjust available handles if needed
    if (media_in_trimmed - media_in) < handle_start:
        handle_start = max(0, media_in_trimmed - media_in)
    if (media_out - media_out_trimmed) < handle_end:
        handle_end = max(0, media_out - media_out_trimmed)

    # FFmpeg extraction ignores embedded timecode
    # so substract to get a (mediaIn-mediaOut) range from 0.
    if not is_input_sequence:
        media_in_trimmed -= media_in
        media_out_trimmed -= media_in

    # create version data
    version_data = {
        "versionData": {
            "retime": True,
            "speed": time_scalar,
            "timewarps": time_warp_nodes,
            "handleStart": int(handle_start),
            "handleEnd": int(handle_end)
        }
    }

    returning_dict = {
        "mediaIn": media_in_trimmed,
        "mediaOut": media_out_trimmed,
        "handleStart": int(handle_start),
        "handleEnd": int(handle_end),
        "speed": time_scalar
    }

    # add version data only if retime
    if time_warp_nodes or time_scalar != 1.:
        returning_dict.update(version_data)

    return returning_dict
