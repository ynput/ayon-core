import unittest
from unittest import mock

from ayon_core.lib.transcoding import (
    get_review_info_by_layer_name,
    get_ffmpeg_codec_args,
)


def _av1_ffprobe_data(width=1920, height=1080, pix_fmt="yuv420p"):
    """Minimal ffprobe payload with a single AV1 video stream."""
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "av1",
                "pix_fmt": pix_fmt,
                "width": width,
                "height": height,
                # Present on purpose: it must NOT be copied to the output.
                "bit_rate": "156000",
            }
        ]
    }


_ENCODERS_PATH = (
    "ayon_core.lib.transcoding.get_ffmpeg_available_encoders"
)


class GetFfmpegCodecArgsAv1(unittest.TestCase):
    """AV1 branch of `get_ffmpeg_codec_args`."""

    def test_defaults_use_libsvtav1(self):
        with mock.patch(_ENCODERS_PATH, return_value={"libsvtav1"}):
            args = get_ffmpeg_codec_args(_av1_ffprobe_data())
        self.assertEqual(args, [
            "-codec:v", "libsvtav1",
            "-preset", "8",
            "-crf", "30",
            "-pix_fmt", "yuv420p",
            "-g", "1",
        ])
        # Source bitrate must never leak into an intra encode.
        self.assertNotIn("-b:v", args)

    def test_source_crf_and_preset_copied(self):
        source = "ffmpeg -i in.mov -crf 28 -preset 6 out.mp4"
        with mock.patch(_ENCODERS_PATH, return_value={"libsvtav1"}):
            args = get_ffmpeg_codec_args(
                _av1_ffprobe_data(), source_ffmpeg_cmd=source
            )
        self.assertEqual(args, [
            "-codec:v", "libsvtav1",
            "-crf", "28",
            "-preset", "6",
            "-pix_fmt", "yuv420p",
            "-g", "1",
        ])

    def test_4k_uses_higher_default_crf(self):
        with mock.patch(_ENCODERS_PATH, return_value={"libsvtav1"}):
            args = get_ffmpeg_codec_args(
                _av1_ffprobe_data(width=3840, height=2160)
            )
        self.assertIn("-crf", args)
        self.assertEqual(args[args.index("-crf") + 1], "32")

    def test_rate_caps_are_not_copied(self):
        # '-maxrate'/'-bufsize' ruin an all-keyframe encode, so they must
        # not be copied even when the studio set them.
        source = (
            "ffmpeg -i in.mov -crf 28 -maxrate 10M -bufsize 20M out.mp4"
        )
        with mock.patch(_ENCODERS_PATH, return_value={"libsvtav1"}):
            args = get_ffmpeg_codec_args(
                _av1_ffprobe_data(), source_ffmpeg_cmd=source
            )
        self.assertIn("-crf", args)
        self.assertNotIn("-maxrate", args)
        self.assertNotIn("-bufsize", args)

    def test_libaom_uses_allintra_without_g(self):
        with mock.patch(_ENCODERS_PATH, return_value={"libaom-av1"}):
            args = get_ffmpeg_codec_args(_av1_ffprobe_data())
        self.assertEqual(args, [
            "-codec:v", "libaom-av1",
            "-crf", "30",
            "-pix_fmt", "yuv420p",
            "-usage", "allintra",
            "-cpu-used", "6",
            "-row-mt", "1",
        ])
        # all-intra provides the keyframes, so no explicit GOP of 1.
        self.assertNotIn("-g", args)

    def test_hardware_encoders_are_not_auto_selected(self):
        # Present in the build but excluded from the automatic pick: fall
        # through to libsvtav1 here, and to bare 'av1' when alone.
        with mock.patch(_ENCODERS_PATH,
                        return_value={"av1_nvenc", "libsvtav1"}):
            args = get_ffmpeg_codec_args(_av1_ffprobe_data())
        self.assertEqual(args[:2], ["-codec:v", "libsvtav1"])

        with mock.patch(_ENCODERS_PATH,
                        return_value={"av1_nvenc", "av1_qsv"}):
            args = get_ffmpeg_codec_args(_av1_ffprobe_data())
        self.assertEqual(args[:2], ["-codec:v", "av1"])

    def test_falls_back_to_bare_av1_when_none_available(self):
        with mock.patch(_ENCODERS_PATH, return_value=set()):
            args = get_ffmpeg_codec_args(_av1_ffprobe_data())
        self.assertEqual(args[:2], ["-codec:v", "av1"])


class GetReviewInfoByLayerName(unittest.TestCase):
    """Test responses from `get_review_info_by_layer_name`"""
    def test_rgba_channels(self):

        # RGB is supported
        info = get_review_info_by_layer_name(["R", "G", "B"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "R",
                "G": "G",
                "B": "B",
                "A": None,
            }
        }])

        # rgb is supported
        info = get_review_info_by_layer_name(["r", "g", "b"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "r",
                "G": "g",
                "B": "b",
                "A": None,
            }
        }])

        # diffuse.[RGB] is supported
        info = get_review_info_by_layer_name(
            ["diffuse.R", "diffuse.G", "diffuse.B"]
        )
        self.assertEqual(info, [{
            "name": "diffuse",
            "review_channels": {
                "R": "diffuse.R",
                "G": "diffuse.G",
                "B": "diffuse.B",
                "A": None,
            }
        }])

        info = get_review_info_by_layer_name(["R", "G", "B", "A"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "R",
                "G": "G",
                "B": "B",
                "A": "A",
            }
        }])

    def test_z_channel(self):

        info = get_review_info_by_layer_name(["Z"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "Z",
                "G": "Z",
                "B": "Z",
                "A": None,
            }
        }])

        info = get_review_info_by_layer_name(["Z", "A"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "Z",
                "G": "Z",
                "B": "Z",
                "A": "A",
            }
        }])

    def test_ar_ag_ab_channels(self):

        info = get_review_info_by_layer_name(["AR", "AG", "AB"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "AR",
                "G": "AG",
                "B": "AB",
                "A": None,
            }
        }])

        info = get_review_info_by_layer_name(["AR", "AG", "AB", "A"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "AR",
                "G": "AG",
                "B": "AB",
                "A": "A",
            }
        }])

    def test_unknown_channels(self):
        info = get_review_info_by_layer_name(["hello", "world"])
        self.assertEqual(info, [])

    def test_rgba_priority(self):
        """Ensure main layer, and RGB channels are prioritized

        If both Z and RGB channels are present for a layer name, then RGB
        should be prioritized and the Z channel should be ignored.

        Also, the alpha channel from another "layer name" is not used. Note
        how the diffuse response does not take A channel from the main layer.

        """

        info = get_review_info_by_layer_name([
            "Z",
            "diffuse.R", "diffuse.G", "diffuse.B",
            "R", "G", "B", "A",
            "specular.R", "specular.G", "specular.B", "specular.A",
        ])
        self.assertEqual(info, [
            {
                "name": "",
                "review_channels": {
                    "R": "R",
                    "G": "G",
                    "B": "B",
                    "A": "A",
                },
            },
            {
                "name": "diffuse",
                "review_channels": {
                    "R": "diffuse.R",
                    "G": "diffuse.G",
                    "B": "diffuse.B",
                    "A": None,
                },
            },
            {
                "name": "specular",
                "review_channels": {
                    "R": "specular.R",
                    "G": "specular.G",
                    "B": "specular.B",
                    "A": "specular.A",
                },
            },
        ])
