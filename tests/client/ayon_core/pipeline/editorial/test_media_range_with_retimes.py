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


def test_movie_23fps_qt_embedded_tc():
    """
    Movie clip (embedded timecode 1h)
    available_range = 1937896-1937994 23.976fps
    source_range = 1937905-1937987 23.97602462768554fps
    """
    expected_data = {
        'mediaIn': 1009,
        'mediaOut': 1090,
        'handleStart': 8,
        'handleEnd': 8,
        'speed': 1.0
    }

    _check_expected_retimed_values(
        "qt_23.976_embedded_long_tc.json",
        expected_data,
        handle_start=8,
        handle_end=8,
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


def test_movie_reverse_speed_2x():
    """
    Movie clip (no timecode)
    available files = 0-100 24fps
    source_range =  29.97-40.97 23.976fps
    speed = -2.0
    """
    expected_data = {
        # not exactly 30 because of 23.976 rouding
        # https://github.com/AcademySoftwareFoundation/
        # OpenTimelineIO/issues/1822
        'mediaIn': 30.000000000000004,
        'mediaOut': 51.02199940144827,
        'handleStart': 20,
        'handleEnd': 20,
        'speed': -2.0,
        'versionData': {
            'retime': True,
            'speed': -2.0,
            'timewarps': [],
            'handleStart': 20,
            'handleEnd': 20,
        }
    }

    _check_expected_retimed_values(
        "qt_reverse_speed_2x.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_movie_reverse_speed_0_7x():
    """
    Movie clip (no timecode)
    available files = 0-100 24fps
    source_range =  29.97-40.97 23.976fps
    speed = -0.7
    """
    expected_data = {
        'handleEnd': 7,
        'handleStart': 7,
        'mediaIn': 30.000000000000004,
        'mediaOut': 36.70769965924555,
        'speed': -0.699999988079071,
        'versionData': {
            'handleEnd': 7,
            'handleStart': 7,
            'retime': True,
            'speed': -0.699999988079071,
            'timewarps': []
        }
    }

    _check_expected_retimed_values(
        "qt_reverse_speed_0_7.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_movie_frozen_frame():
    """
    Movie clip (no timecode)
    available files = 0-100 24fps
    source_range =  29.97-40.97 23.976fps
    speed = 0.0
    """
    expected_data = {
        # not exactly 30 because of OTIO rounding
        # https://github.com/AcademySoftwareFoundation/
        # OpenTimelineIO/issues/1822
        'mediaIn': 30.000000000000004,
        'mediaOut': 30.000000000000004,
        'handleStart': 0,
        'handleEnd': 0,
        'speed': 0.0,
        'versionData': {
            'retime': True,
            'speed': 0.0,
            'timewarps': [],
            'handleStart': 0,
            'handleEnd': 0,
        }
    }

    _check_expected_retimed_values(
        "qt_freeze_frame.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_movie_timewarp():
    """
    Movie clip (no timecode)
    available files = 0-100 24fps
    source_range =  29.97-40.97 23.976fps
    speed = timewarp
    """
    expected_data = {
        'handleEnd': 10,
        'handleStart': 0,
        'mediaIn': 948850,
        'mediaOut': 948860,
        'speed': 1.0,
        'versionData': {'handleEnd': 10,
             'handleStart': 0,
             'retime': True,
             'speed': 1.0,
             'timewarps': [
                {
                    'Class': 'TimeWarp',
                    'length': 4.0,
                    'lookup': [
                        2.0,
                        1.8959999809265136,
                        1.767999971389771,
                        1.59199997138977,
                        1.3439999809265135,
                        1.0,
                        0.5440000181198119,
                        -0.007999974250793684,
                        -0.6319999756813051,
                        -1.3039999847412114,
                        -2.0
                    ],
                    'name': 'TimeWarp2'
                }
            ]
        }
    }

    _check_expected_retimed_values(
        "qt_timewarp.json",
        expected_data,
        handle_start=0,
        handle_end=10,
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


def test_img_sequence_conform_from_24_to_23_976fps():
    """
    Img sequence clip
    available files = 883750-884504 24fps
    source_range =  883159-883267 23.976fps

    This test ensures such entries do not trigger
    the legacy Hiero export compatibility.
    """
    expected_data = {
        'mediaIn': 884043,
        'mediaOut': 884150,
        'handleStart': 0,
        'handleEnd': 0,
        'speed': 1.0
    }

    _check_expected_retimed_values(
        "img_seq_24_to_23.976_no_legacy.json",
        expected_data,
        handle_start=0,
        handle_end=0,
    )


def test_img_sequence_reverse_speed_no_tc():
    """
    Img sequence clip
    available files = 0-100 24fps
    source_range =  20-41 24fps
    """
    expected_data = {
        'mediaIn': 1020,
        'mediaOut': 1060,
        'handleStart': 0,
        'handleEnd': 0,
        'speed': -1.0,
        'versionData': {
            'retime': True,
            'speed': -1.0,
            'timewarps': [],
            'handleStart': 0,
            'handleEnd': 0
        }
    }

    _check_expected_retimed_values(
        "img_seq_reverse_speed_no_tc.json",
        expected_data,
        handle_start=0,
        handle_end=0,
    )

def test_img_sequence_reverse_speed_from_24_to_23_976fps():
    """
    Img sequence clip
    available files = 941478-949084 24fps
    source_range =  947726-947757 23.976fps
    """
    expected_data = {
        'mediaIn': 948674,
        'mediaOut': 948705,
        'handleStart': 10,
        'handleEnd': 10,
        'speed': -1.0,
        'versionData': {
            'retime': True,
            'speed': -1.0,
            'timewarps': [],
            'handleStart': 10,
            'handleEnd': 10
        }
    }

    _check_expected_retimed_values(
        "img_seq_reverse_speed_24_to_23.976fps.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_img_sequence_2x_speed():
    """
    Img sequence clip
    available files = 948674-948974 25fps
    source_range =  948850-948870 23.976fps
    speed = 2.0
    """
    expected_data = {
        'mediaIn': 948850,
        'mediaOut': 948871,
        'handleStart': 20,
        'handleEnd': 20,
        'speed': 2.0,
        'versionData': {
            'retime': True,
            'speed': 2.0,
            'timewarps': [],
            'handleStart': 20,
            'handleEnd': 20
        }
    }

    _check_expected_retimed_values(
        "img_seq_2x_speed.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_img_sequence_2x_speed_resolve():
    """
    Img sequence clip
    available files = 0-99 24fps
    source_range =  38-49 24fps
    speed = 2.0
    """
    expected_data = {
        'mediaIn': 1040,
        'mediaOut': 1061,
        'handleStart': 20,
        'handleEnd': 20,
        'speed': 2.0,
        'versionData': {
            'retime': True,
            'speed': 2.0,
            'timewarps': [],
            'handleStart': 20,
            'handleEnd': 20
        }
    }

    _check_expected_retimed_values(
        "img_seq_2x_speed_resolve.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_img_sequence_frozen_frame():
    """
    Img sequence clip
    available files = 948674-948974 25fps
    source_range =  909990.8339241028 
                - 909995.8339241028 23.976fps
    speed = 0.0
    """
    expected_data = {
        'mediaIn': 948855,
        'mediaOut': 948855,
        'handleStart': 0,
        'handleEnd': 0,
        'speed': 0.0,
        'versionData': {
            'retime': True,
            'speed': 0.0,
            'timewarps': [],
            'handleStart': 0,
            'handleEnd': 0,
        }
    }

    _check_expected_retimed_values(
        "img_seq_freeze_frame.json",
        expected_data,
        handle_start=10,
        handle_end=10,
    )


def test_img_sequence_timewarp_beyond_range():
    """
    Img sequence clip
    available files = 948674-948974 25fps
    source_range =  909990.8339241028 
                - 909995.8339241028 23.976fps
    timewarp to get from 948845 to 948870
    """
    expected_data = {
        'mediaIn': 948845,
        'mediaOut': 948870,
        'handleStart': 0,
        'handleEnd': 10,
        'speed': 1.0,
        'versionData': {'handleEnd': 10,
             'handleStart': 0,
             'retime': True,
             'speed': 1.0,
             'timewarps': [
                {
                    'Class': 'TimeWarp',
                    'length': 1.0,
                    'lookup': [
                        -5.0,
                        -3.9440000305175777,
                        -2.852000034332275,
                        -1.6880000228881844,
                        -0.4160000076293944,
                        1.0,
                        2.5839999923706056,
                        4.311999977111817,
                        6.147999965667726,
                        8.055999969482421,
                        10.0
                    ],
                    'name': 'TimeWarp3'
                }
            ]
        }
    }

    _check_expected_retimed_values(
        "img_seq_tw_beyond_range.json",
        expected_data,
        handle_start=0,
        handle_end=10,
    )


def test_img_sequence_2X_speed_timewarp():
    """
    Img sequence clip
    available files = 948674-948974 25fps
    source_range =  909990.8339241028 
                - 909995.8339241028 23.976fps
    speed: 200%
    timewarp to get from 948854 to 948874
    """
    expected_data = {
        'mediaIn': 948850,
        'mediaOut': 948874,
        'handleStart': 0,
        'handleEnd': 20,
        'speed': 2.0,
        'versionData': {
            'handleEnd': 20,
            'handleStart': 0,
            'retime': True,
            'speed': 2.0,
            'timewarps': [
                {
                    'Class': 'TimeWarp',
                    'length': 4.0,
                    'lookup': [
                        2.0,
                        1.7039999923706055,
                        1.431999991416931,
                        1.2079999942779531,
                        1.055999998092652,
                        1.0,
                        1.056000007629395,
                        1.208000022888184,
                        1.432000034332276,
                        1.7040000305175766,
                        2.0
                    ],
                    'name': 'TimeWarp6'
                }
            ]
        }
    }

    _check_expected_retimed_values(
        "img_seq_2x_time_warp.json",
        expected_data,
        handle_start=0,
        handle_end=10,
    )


def test_img_sequence_multiple_timewarps():
    """
    Img sequence clip
    available files = 948674-948974 25fps
    source_range =  909990.8339241028 
                - 909995.8339241028 23.976fps
    multiple timewarps to get from 948842 to 948864
    """
    expected_data = {
        'mediaIn': 948845,
        'mediaOut': 948867,
        'handleStart': 0,
        'handleEnd': 10,
        'speed': 1.0,
        'versionData': {
            'handleEnd': 10,
            'handleStart': 0,
            'retime': True,
            'speed': 1.0,
            'timewarps': [
                {
                    'Class': 'TimeWarp',
                    'length': 1.0,
                    'lookup': [
                        -5.0,
                        -3.9440000305175777,
                        -2.852000034332275,
                        -1.6880000228881844,
                        -0.4160000076293944,
                        1.0,
                        2.5839999923706056,
                        4.311999977111817,
                        6.147999965667726,
                        8.055999969482421,
                        10.0
                    ],
                    'name': 'TimeWarp3'
                },
                {
                    'Class': 'TimeWarp',
                    'length': 1.0,
                    'lookup': [
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0
                    ],
                    'name': 'TimeWarp4'
                },
                {
                    'Class': 'TimeWarp',
                    'length': 1.0,
                    'lookup': [
                        0.0,
                        -1.0,
                        1.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        -1.0
                    ],
                    'name': 'TimeWarp5'
                }
            ]
        }
    }

    _check_expected_retimed_values(
        "img_seq_multiple_tws.json",
        expected_data,
        handle_start=0,
        handle_end=10,
    )
