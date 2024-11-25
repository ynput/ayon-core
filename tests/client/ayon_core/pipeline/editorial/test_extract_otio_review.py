import mock
import os
import pytest  # noqa
from typing import NamedTuple

import opentimelineio as otio

from ayon_core.plugins.publish import extract_otio_review


_RESOURCE_DIR = os.path.join(
    os.path.dirname(__file__),
    "resources"
)


class MockInstance():
    """ Mock pyblish instance for testing purpose.
    """
    def __init__(self, data: dict):
        self.data = data
        self.context = self


class CaptureFFmpegCalls():
    """ Mock calls made to ffmpeg subprocess.
    """
    def __init__(self):
        self.calls = []

    def append_call(self, *args, **kwargs):
        ffmpeg_args_list, = args
        self.calls.append(" ".join(ffmpeg_args_list))
        return True

    def get_ffmpeg_executable(self, _):
        return ["/path/to/ffmpeg"]


def run_process(file_name: str, instance_data: dict = None):
    """
    """
    # Prepare dummy instance and capture call object
    capture_call = CaptureFFmpegCalls()
    processor = extract_otio_review.ExtractOTIOReview()
    Anatomy = NamedTuple("Anatomy", project_name=str)

    if not instance_data:
        # Get OTIO review data from serialized file_name
        file_path = os.path.join(_RESOURCE_DIR, file_name)
        clip = otio.schema.Clip.from_json_file(file_path)

        instance_data = {
            "otioReviewClips": [clip],
            "handleStart": 10,
            "handleEnd": 10,
            "workfileFrameStart": 1001,
        }

    instance_data.update({
        "folderPath": "/dummy/path",
        "anatomy": Anatomy("test_project"),
    })
    instance = MockInstance(instance_data)

    # Mock calls to extern and run plugins.
    with mock.patch.object(
        extract_otio_review,
        "get_ffmpeg_tool_args",
        side_effect=capture_call.get_ffmpeg_executable,
    ):
        with mock.patch.object(
            extract_otio_review,
            "run_subprocess",
            side_effect=capture_call.append_call,
        ):
            with mock.patch.object(
                processor,
                "_get_folder_name_based_prefix",
                return_value="output."
            ):
                with mock.patch.object(
                    processor,
                    "staging_dir",
                    return_value="C:/result/"
                ):
                    processor.process(instance)

    # return all calls made to ffmpeg subprocess
    return capture_call.calls


def test_image_sequence_with_embedded_tc_and_handles_out_of_range():
    """
    Img sequence clip (embedded timecode 1h/24fps)
    available_files = 1000-1100
    available_range = 87399-87500 24fps
    source_range = 87399-87500 24fps
    """
    calls = run_process("img_seq_embedded_tc_review.json")

    expected = [
        # 10 head black handles generated from gap (991-1000)
        "/path/to/ffmpeg -t 0.4166666666666667 -r 24.0 -f lavfi -i "
        "color=c=black:s=1280x720 -tune stillimage -start_number 991 "
        "C:/result/output.%03d.jpg",

        # 10 tail black handles generated from gap (1102-1111)
        "/path/to/ffmpeg -t 0.4166666666666667 -r 24.0 -f lavfi -i "
        "color=c=black:s=1280x720 -tune stillimage -start_number 1102 "
        "C:/result/output.%03d.jpg",

        # Report from source exr (1001-1101) with enforce framerate
        "/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i "
        f"C:\\exr_embedded_tc{os.sep}output.%04d.exr -start_number 1001 "
        "C:/result/output.%03d.jpg"
    ]

    assert calls == expected


def test_image_sequence_and_handles_out_of_range():
    """
    Img sequence clip (no timecode)
    available_files = 1000-1100
    available_range = 0-101 25fps
    source_range = 5-91 24fps
    """
    calls = run_process("img_seq_review.json")

    expected = [
        # 5 head black frames generated from gap (991-995)
        "/path/to/ffmpeg -t 0.2 -r 25.0 -f lavfi -i color=c=black:s=1280x720"
        " -tune stillimage -start_number 991 C:/result/output.%03d.jpg",

        # 9 tail back frames generated from gap (1097-1105)
        "/path/to/ffmpeg -t 0.36 -r 25.0 -f lavfi -i color=c=black:s=1280x720"
        " -tune stillimage -start_number 1097 C:/result/output.%03d.jpg",

        # Report from source tiff (996-1096)
        # 996-1000 = additional 5 head frames
        # 1001-1095 = source range conformed to 25fps
        # 1096-1096 = additional 1 tail frames
        "/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i "
        f"C:\\tif_seq{os.sep}output.%04d.tif -start_number 996"
        f" C:/result/output.%03d.jpg"
    ]

    assert calls == expected


def test_movie_with_embedded_tc_no_gap_handles():
    """
    Qt movie clip (embedded timecode 1h/24fps)
    available_range = 86400-86500 24fps
    source_range = 86414-86482 24fps
    """
    calls = run_process("qt_embedded_tc_review.json")

    expected = [
        # Handles are all included in media available range.
        # Extract source range from Qt
        # - first_frame = 14 src - 10 (head tail) = frame 4 = 0.1666s
        # - duration = 68fr (source) + 20fr (handles) = 88frames = 3.666s
        "/path/to/ffmpeg -ss 0.16666666666666666 -t 3.6666666666666665 "
        "-i C:\\data\\qt_embedded_tc.mov -start_number 991 "
        "C:/result/output.%03d.jpg"
    ]

    assert calls == expected


def test_short_movie_head_gap_handles():
    """
    Qt movie clip.
    available_range = 0-30822 25fps
    source_range = 0-50 24fps
    """
    calls = run_process("qt_review.json")

    expected = [
        # 10 head black frames generated from gap (991-1000)
        "/path/to/ffmpeg -t 0.4 -r 25.0 -f lavfi -i color=c=black:s=1280x720"
        " -tune stillimage -start_number 991 C:/result/output.%03d.jpg",

        # source range + 10 tail frames
        # duration = 50fr (source) + 10fr (tail handle) = 60 fr = 2.4s
        "/path/to/ffmpeg -ss 0.0 -t 2.4 -i C:\\data\\movie.mp4"
        " -start_number 1001 C:/result/output.%03d.jpg"
    ]

    assert calls == expected


def test_short_movie_tail_gap_handles():
    """
    Qt movie clip.
    available_range = 0-101 24fps
    source_range = 35-101 24fps
    """
    calls = run_process("qt_handle_tail_review.json")

    expected = [
        # 10 tail black frames generated from gap (1067-1076)
        "/path/to/ffmpeg -t 0.4166666666666667 -r 24.0 -f lavfi -i "
        "color=c=black:s=1280x720 -tune stillimage -start_number 1067 "
        "C:/result/output.%03d.jpg",

        # 10 head frames + source range
        # duration = 10fr (head handle) + 66fr (source) = 76fr = 3.16s
        "/path/to/ffmpeg -ss 1.0416666666666667 -t 3.1666666666666665 -i "
        "C:\\data\\qt_no_tc_24fps.mov -start_number 991"
        " C:/result/output.%03d.jpg"
    ]

    assert calls == expected

def test_multiple_review_clips_no_gap():
    """
    Use multiple review clips (image sequence).
    Timeline 25fps
    """
    file_path = os.path.join(_RESOURCE_DIR, "multiple_review_clips.json")
    clips = otio.schema.Track.from_json_file(file_path)
    instance_data = {
        "otioReviewClips": clips,
        "handleStart": 10,
        "handleEnd": 10,
        "workfileFrameStart": 1001,
    }

    calls = run_process(
        None,
        instance_data=instance_data
    )

    expected = [
        # 10 head black frames generated from gap (991-1000)
        '/path/to/ffmpeg -t 0.4 -r 25.0 -f lavfi'
        ' -i color=c=black:s=1280x720 -tune '
        'stillimage -start_number 991 C:/result/output.%03d.jpg',

        # Alternance 25fps tiff sequence and 24fps exr sequence
        #   for 100 frames each
        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1001 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
        f'C:\\with_tc{os.sep}output.%04d.exr '
        '-start_number 1102 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1199 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
        f'C:\\with_tc{os.sep}output.%04d.exr '
        '-start_number 1300 C:/result/output.%03d.jpg',

        # Repeated 25fps tiff sequence multiple times till the end
        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1397 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1498 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1599 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1700 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1801 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 1902 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 2003 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 2104 C:/result/output.%03d.jpg',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-start_number 2205 C:/result/output.%03d.jpg'
    ]

    assert calls == expected

def test_multiple_review_clips_with_gap():
    """
    Use multiple review clips (image sequence) with gap.
    Timeline 24fps
    """
    file_path = os.path.join(_RESOURCE_DIR, "multiple_review_clips_gap.json")
    clips = otio.schema.Track.from_json_file(file_path)
    instance_data = {
        "otioReviewClips": clips,
        "handleStart": 10,
        "handleEnd": 10,
        "workfileFrameStart": 1001,
    }

    calls = run_process(
        None,
        instance_data=instance_data
    )

    expected = [
    # Gap on review track (12 frames)
    '/path/to/ffmpeg -t 0.5 -r 24.0 -f lavfi'
    ' -i color=c=black:s=1280x720 -tune '
    'stillimage -start_number 991 C:/result/output.%03d.jpg',

    '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
    f'C:\\with_tc{os.sep}output.%04d.exr '
    '-start_number 1003 C:/result/output.%03d.jpg',

    '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
    f'C:\\with_tc{os.sep}output.%04d.exr '
    '-start_number 1091 C:/result/output.%03d.jpg'
    ]

    assert calls == expected
