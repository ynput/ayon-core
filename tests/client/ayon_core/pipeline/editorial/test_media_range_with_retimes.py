import os

import opentimelineio as otio

from ayon_core.pipeline.editorial import get_media_range_with_retimes


_RESOURCE_DIR = os.path.join(
    os.path.dirname(__file__),
    "resources"
)


def _check_expected_retimed_values(
    file_name: str,
    expected_retimed_data: dict,
    handle_start: int = 10,
    handle_end: int = 10,
):
    file_path = os.path.join(_RESOURCE_DIR, file_name)
    otio_clip = otio.schema.Clip.from_json_file(file_path)

    retimed_data = get_media_range_with_retimes(
        otio_clip, handle_start, handle_end
    )
    assert retimed_data == expected_retimed_data


def test_movie_with_end_handle_end_only():
    """
    Movie clip (no embedded timecode)
    available_range = 0-171 25fps
    source_range = 0-16450 25fps
    """
    expected_data = {
        'mediaIn': 0.0,
        'mediaOut': 170.0,
        'handleStart': 0,
        'handleEnd': 10,
        'speed': 1.0
    }
    _check_expected_retimed_values(
        "movie_with_handles.json",
        expected_data,
    )


def test_movie_embedded_tc_handle():
    """
    Movie clip (embedded timecode 1h)
    available_range = 86400-86500 24fps
    source_range = 90032-90076 25fps
    """
    expected_data = {
        'mediaIn': 30.720000000001164,
        'mediaOut': 71.9600000000064,
        'handleStart': 10,
        'handleEnd': 10,
        'speed': 1.0
    }
    _check_expected_retimed_values(
        "qt_embedded_tc.json",
        expected_data
    )


def test_movie_retime_effect():
    """
    Movie clip (embedded timecode 1h)
    available_range = 0-171 25fps
    source_range = 0-16450 25fps
    retimed speed: 250%
    """
    expected_data = {
        'mediaIn': 0.0,
        'mediaOut': 426.5,
        'handleStart': 0,
        'handleEnd': 25,
        'speed': 2.5,
        'versionData': {
            'retime': True,
            'speed': 2.5,
            'timewarps': [],
            'handleStart': 0,
            'handleEnd': 25
        }
    }
    _check_expected_retimed_values(
        "qt_retimed_speed.json",
        expected_data
    )


def test_img_sequence_no_handles():
    """
    Img sequence clip (no embedded timecode)
    available files = 1000-1100
    source_range =  0-100 25fps
    """
    expected_data = {
        'mediaIn': 1000,
        'mediaOut': 1100,
        'handleStart': 0,
        'handleEnd': 0,
        'speed': 1.0
    }
    _check_expected_retimed_values(
        "img_seq_no_handles.json",
        expected_data
    )


def test_img_sequence_with_handles():
    """
    Img sequence clip (no embedded timecode)
    available files = 1000-1100
    source_range =  34-72 25fps
    """
    expected_data = {
        'mediaIn': 1034,
        'mediaOut': 1072,
        'handleStart': 10,
        'handleEnd': 10,
        'speed': 1.0
    }
    _check_expected_retimed_values(
        "img_seq_with_handles.json",
        expected_data
    )


def test_img_sequence_with_embedded_tc_and_handles():
    """
    Img sequence clip (embedded timecode 1h)
    available files = 1000-1100
    source_range =  91046.625-91120.625 25fps
    """
    expected_data = {
        'mediaIn': 1005,
        'mediaOut': 1075,
        'handleStart': 5,
        'handleEnd': 10,
        'speed': 1.0
    }
    _check_expected_retimed_values(
        "img_seq_embedded_tc.json",
        expected_data
    )


def test_img_sequence_relative_source_range():
    """
    Img sequence clip (embedded timecode 1h)
    available files = 1000-1100
    source_range =  fps
    """
    expected_data = {
        'mediaIn': 1000,
        'mediaOut': 1098,
        'handleStart': 0,
        'handleEnd': 2,
        'speed': 1.0
    }

    _check_expected_retimed_values(
        "legacy_img_sequence.json",
        expected_data
    )

def test_img_sequence_conform_to_23_976fps():
    """
    Img sequence clip
    available files = 997-1047 23.976fps
    source_range =  997-1055 23.976024627685547fps
    """
    expected_data = {
        'mediaIn': 997,
        'mediaOut': 1047,
        'handleStart': 0,
        'handleEnd': 8,
        'speed': 1.0
    }

    _check_expected_retimed_values(
        "img_seq_23.976_metadata.json",
        expected_data,
        handle_start=0,
        handle_end=8,
    )
