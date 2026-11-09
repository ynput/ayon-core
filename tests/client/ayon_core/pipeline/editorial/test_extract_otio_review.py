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
        "-pix_fmt rgba C:/result/output.%04d.png",

        # 10 tail black handles generated from gap (1102-1111)
        "/path/to/ffmpeg -t 0.4166666666666667 -r 24.0 -f lavfi -i "
        "color=c=black:s=1280x720 -tune stillimage -start_number 1102 "
        "-pix_fmt rgba C:/result/output.%04d.png",

        # Report from source exr (1001-1101) with enforce framerate
        "/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i "
        f"C:\\exr_embedded_tc{os.sep}output.%04d.exr "
        "-vf scale=1280:720:flags=lanczos -compression_level 5 -frames:v 101 "
        "-start_number 1001 -pix_fmt rgba C:/result/output.%04d.png"
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
        "/path/to/ffmpeg -t 0.2 -r 25.0 -f lavfi -i color=c=black:s=1280x720 "
        "-tune stillimage -start_number 991 -pix_fmt rgba "
        "C:/result/output.%04d.png",

        # 9 tail back frames generated from gap (1097-1105)
        "/path/to/ffmpeg -t 0.36 -r 25.0 -f lavfi -i color=c=black:s=1280x720 "
        "-tune stillimage -start_number 1097 -pix_fmt rgba "
        "C:/result/output.%04d.png",

        # Report from source tiff (996-1096)
        # 996-1000 = additional 5 head frames
        # 1001-1095 = source range conformed to 25fps
        # 1096-1096 = additional 1 tail frames
        "/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i "
        f"C:\\tif_seq{os.sep}output.%04d.tif "
        "-vf scale=1280:720:flags=lanczos -compression_level 5 -frames:v 101 "
        "-start_number 996 -pix_fmt rgba C:/result/output.%04d.png"
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
        "-i C:\\data\\qt_embedded_tc.mov -vf scale=1280:720:flags=lanczos "
        "-compression_level 5 -frames:v 88 -start_number 991 -pix_fmt rgba "
        "C:/result/output.%04d.png"
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
        " -tune stillimage -start_number 991 -pix_fmt rgba "
        "C:/result/output.%04d.png",

        # source range + 10 tail frames
        # duration = 50fr (source) + 10fr (tail handle) = 60 fr = 2.4s
        "/path/to/ffmpeg -ss 0.0 -t 2.4 -i C:\\data\\movie.mp4 -vf "
        "scale=1280:720:flags=lanczos -compression_level 5 -frames:v 60 "
        "-start_number 1001 -pix_fmt rgba C:/result/output.%04d.png"
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
        "-pix_fmt rgba C:/result/output.%04d.png",

        # 10 head frames + source range
        # duration = 10fr (head handle) + 66fr (source) = 76fr = 3.16s
        "/path/to/ffmpeg -ss 1.0416666666666667 -t 3.1666666666666665 -i "
        "C:\\data\\qt_no_tc_24fps.mov -vf scale=1280:720:flags=lanczos "
        "-compression_level 5 -frames:v 76 -start_number 991 -pix_fmt rgba "
        "C:/result/output.%04d.png"
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
        ' -i color=c=black:s=1920x1080 -tune '
        'stillimage -start_number 991 -pix_fmt rgba C:/result/output.%04d.png',

        # Alternance 25fps tiff sequence and 24fps exr sequence
        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1001 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
        f'C:\\with_tc{os.sep}output.%04d.exr '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 96 '
        '-start_number 1102 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1198 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
        f'C:\\with_tc{os.sep}output.%04d.exr '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 96 '
        '-start_number 1299 -pix_fmt rgba C:/result/output.%04d.png',

        # Repeated 25fps tiff sequence multiple times till the end
        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1395 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1496 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1597 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1698 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1799 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 1900 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 2001 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 101 '
        '-start_number 2102 -pix_fmt rgba C:/result/output.%04d.png',

        '/path/to/ffmpeg -start_number 1000 -framerate 25.0 -i '
        f'C:\\no_tc{os.sep}output.%04d.tif '
        '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 41 '
        '-start_number 2203 -pix_fmt rgba C:/result/output.%04d.png'
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
    'stillimage -start_number 991 -pix_fmt rgba C:/result/output.%04d.png',

    '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
    f'C:\\with_tc{os.sep}output.%04d.exr '
    '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 88 '
    '-start_number 1003 -pix_fmt rgba C:/result/output.%04d.png',

    '/path/to/ffmpeg -start_number 1000 -framerate 24.0 -i '
    f'C:\\with_tc{os.sep}output.%04d.exr '
    '-vf scale=1920:1080:flags=lanczos -compression_level 5 -frames:v 21 '
    '-start_number 1091 -pix_fmt rgba C:/result/output.%04d.png'
    ]

    assert calls == expected


def _clip_with_ranges(media_reference, source_range):
    return otio.schema.Clip(
        name="shot",
        source_range=source_range,
        media_reference=media_reference,
    )


def test_movie_resolve_subframe_source_start():
    """
    Qt movie review clip as exported natively by Resolve at 24000/1001.
    available_range = 86400-86616
    source_range = 86423.99765 (sub-frame) - 86475.99765
    Seek must land on frame 14 (24 - 10 handles), not 13.
    """
    rate = 24000 / 1001
    clip = _clip_with_ranges(
        otio.schema.ExternalReference(
            target_url="C:\\data\\reference.mov",
            available_range=otio.opentime.range_from_start_end_time(
                otio.opentime.RationalTime(86400.0, rate),
                otio.opentime.RationalTime(86616.0, rate),
            ),
        ),
        otio.opentime.TimeRange(
            otio.opentime.RationalTime(86423.99765167243, rate),
            otio.opentime.RationalTime(52.0, rate),
        ),
    )
    calls = run_process(None, instance_data={
        "otioReviewClips": [clip],
        "handleStart": 10,
        "handleEnd": 10,
        "workfileFrameStart": 1001,
    })

    expected = [
        "/path/to/ffmpeg -ss 0.5839166666666666 -t 3.0029999999999997 "
        "-i C:\\data\\reference.mov -vf scale=1280:720:flags=lanczos "
        "-compression_level 5 -frames:v 72 -start_number 991 -pix_fmt rgba "
        "C:/result/output.%04d.png"
    ]

    assert calls == expected


def test_img_sequence_hiero_float32_rate_keeps_last_frame():
    """
    Img sequence clip as exported by Hiero: source range at the float32
    sequence rate, available range at 23.976.
    available_files = 997-1056 (60 frames, 4 frames handles)
    source_range = 52 frames @ 23.976024627685547
    Duration rescales to 51.99995 and must not lose the last frame.
    """
    f32_rate = 23.976024627685547
    media_rate = 23.976
    clip = _clip_with_ranges(
        otio.schema.ImageSequenceReference(
            target_url_base="C:\\exr_hiero",
            name_prefix="output.",
            name_suffix=".exr",
            start_frame=997,
            frame_zero_padding=4,
            rate=media_rate,
            available_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(86396.0, media_rate),
                otio.opentime.RationalTime(60.0, media_rate),
            ),
        ),
        otio.opentime.TimeRange(
            otio.opentime.RationalTime(86400.0, media_rate).rescaled_to(
                f32_rate),
            otio.opentime.RationalTime(52.0, f32_rate),
        ),
    )
    calls = run_process(None, instance_data={
        "otioReviewClips": [clip],
        "handleStart": 4,
        "handleEnd": 4,
        "workfileFrameStart": 1001,
    })

    expected = [
        "/path/to/ffmpeg -start_number 997 -framerate 23.976 -i "
        f"C:\\exr_hiero{os.sep}output.%04d.exr "
        "-vf scale=1280:720:flags=lanczos "
        "-compression_level 5 -frames:v 60 -start_number 997 -pix_fmt rgba "
        "C:/result/output.%04d.png"
    ]

    assert calls == expected
