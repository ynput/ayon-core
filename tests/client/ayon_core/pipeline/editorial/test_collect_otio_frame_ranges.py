import os

import opentimelineio as otio

from ayon_core.plugins.publish import collect_otio_frame_ranges


_RESOURCE_DIR = os.path.join(
    os.path.dirname(__file__),
    "resources",
    "timeline"
)


class MockInstance():
    """ Mock pyblish instance for testing purpose.
    """
    def __init__(self, data: dict):
        self.data = data
        self.context = self


def _check_expected_frame_range_values(
    clip_name: str,
    expected_data: dict,
    handle_start: int = 10,
    handle_end: int = 10,
    retimed: bool = False,
):
    file_path = os.path.join(_RESOURCE_DIR, "timeline.json")
    otio_timeline = otio.schema.Timeline.from_json_file(file_path)

    for otio_clip in otio_timeline.find_clips():
        if otio_clip.name == clip_name:
            break

    instance_data = {
        "otioClip": otio_clip,
        "handleStart": handle_start,
        "handleEnd": handle_end,
        "workfileFrameStart": 1001,
    }
    if retimed:
        instance_data["shotDurationFromSource"] = True

    instance = MockInstance(instance_data)

    processor = collect_otio_frame_ranges.CollectOtioRanges()
    processor.process(instance)

    # Assert expected data is subset of edited instance.
    assert expected_data.items() <= instance.data.items()


def test_movie_with_timecode():
    """
    Movie clip (with embedded timecode)
    available_range = 86531-86590 23.976fps
    source_range = 86535-86586 23.976fps
    """
    expected_data = {
        'frameStart': 1001,
        'frameEnd': 1052,
        'clipIn': 24,
        'clipOut': 75,
        'clipInH': 14,
        'clipOutH': 85,
        'sourceStart': 86535,
        'sourceStartH': 86525,
        'sourceEnd': 86586,
        'sourceEndH': 86596,
    }

    _check_expected_frame_range_values(
        "sh010",
        expected_data,
    )


def test_image_sequence():
    """
    EXR image sequence.
    available_range = 87399-87482 24fps
    source_range = 87311-87336 23.976fps
    """
    expected_data = {
        'frameStart': 1001,
        'frameEnd': 1026,
        'clipIn': 76,
        'clipOut': 101,
        'clipInH': 66,
        'clipOutH': 111,
        'sourceStart': 87399,
        'sourceStartH': 87389,
        'sourceEnd': 87424,
        'sourceEndH': 87434,
    }

    _check_expected_frame_range_values(
        "img_sequence_exr",
        expected_data,
    )


def test_media_retimed():
    """
    EXR image sequence.
    available_range = 345619-345691 23.976fps
    source_range = 345623-345687 23.976fps
    TimeWarp = frozen frame.
    """
    expected_data = {
        'frameStart': 1001,
        'frameEnd': 1065,
        'clipIn': 127,
        'clipOut': 191,
        'clipInH': 117,
        'clipOutH': 201,
        'sourceStart': 1001,
        'sourceStartH': 1001,
        'sourceEnd': 1065,
        'sourceEndH': 1065,
    }

    _check_expected_frame_range_values(
        "P01default_twsh010",
        expected_data,
        retimed=True,
    )
