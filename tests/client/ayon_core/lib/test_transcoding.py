import unittest
from unittest.mock import patch

from ayon_core.lib.transcoding import (
    get_review_info_by_layer_name,
    oiio_color_convert,
)


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


class OiioColorConvertDisplayViewCommands(unittest.TestCase):
    """Regression tests for oiio_color_convert's display/view handling.

    These cover the branches for converting FROM a source display/view
    pair, which historically needed a two-step oiiotool invocation
    ('--ociodisplay:inverse=1' to land in the OCIO reference space,
    followed by a second call out of it) since there is no direct
    display/view-to-colorspace command.

    For a display/view -> colorspace target, that second step used to be
    a '--colorconvert' out of the config's 'scene_linear' role - which is
    not guaranteed to be the same colorspace as the config's actual
    reference space (e.g. ACES 1.x configs commonly point 'scene_linear'
    at ACEScg (AP1) while the reference space is ACES2065-1 (AP0), a
    distinct colorspace related to it by a real gamut matrix). Mislabeling
    the inverted image that way applied that matrix where it didn't
    belong, shifting hue/saturation on saturated colors. The fix does the
    whole conversion as a single oiiotool call via '--ociodisplay's
    'from=' modifier, so no intermediate colorspace is ever named.

    For a display/view -> a *different* display/view target, both legs
    are plain '--ociodisplay' calls that never need to name the reference
    space either way, so that branch is unaffected and still two calls.
    """

    def setUp(self):
        # oiio_color_convert calls get_oiio_info_for_input (which shells
        # out to oiiotool itself) purely to figure out RGBA channel names;
        # stub it so the test needs neither a real oiiotool binary nor an
        # actual input file.
        info_patcher = patch(
            "ayon_core.lib.transcoding.get_oiio_info_for_input",
            return_value={"channelnames": ["R", "G", "B"]},
        )
        self.addCleanup(info_patcher.stop)
        info_patcher.start()

        # get_oiio_tool_args normally resolves a real oiiotool binary
        # path; stub it to mirror its real behaviour of prefixing extra
        # args with the tool name, without needing that binary present.
        tool_args_patcher = patch(
            "ayon_core.lib.transcoding.get_oiio_tool_args",
            side_effect=lambda tool_name, *extra_args: [
                tool_name, *extra_args
            ],
        )
        self.addCleanup(tool_args_patcher.stop)
        tool_args_patcher.start()

        run_subprocess_patcher = patch(
            "ayon_core.lib.transcoding.run_subprocess"
        )
        self.addCleanup(run_subprocess_patcher.stop)
        self.run_subprocess_mock = run_subprocess_patcher.start()

    def _get_oiio_cmd(self):
        """Return the argument list oiiotool was actually called with."""
        self.run_subprocess_mock.assert_called_once()
        args, _kwargs = self.run_subprocess_mock.call_args
        return args[0]

    def test_display_view_to_colorspace_is_single_inverse_ociodisplay(self):
        oiio_color_convert(
            input_path="input.exr",
            output_path="output.exr",
            config_path="config.ocio",
            source_colorspace=None,
            source_display="sRGB - Display",
            source_view="ACES 1.0 - SDR Video",
            target_colorspace="ACES2065-1",
        )

        cmd = self._get_oiio_cmd()

        modifier = "--ociodisplay:from=ACES2065-1:inverse=1:subimages=0"
        self.assertIn(modifier, cmd)
        idx = cmd.index(modifier)
        self.assertEqual(cmd[idx + 1], "sRGB - Display")
        self.assertEqual(cmd[idx + 2], "ACES 1.0 - SDR Video")

        # Single atomic op: no separate colorconvert step, and no other
        # ociodisplay call either.
        self.assertFalse(
            any(arg.startswith("--colorconvert") for arg in cmd)
        )
        self.assertEqual(
            sum(1 for arg in cmd if arg.startswith("--ociodisplay")), 1
        )

    def test_display_view_to_colorspace_keeps_spaced_name_intact(self):
        # Real OCIO display-referred colorspace names (e.g. from an ACES
        # config) commonly contain spaces - they must land intact in a
        # single modifier argument, not get split apart on whitespace.
        oiio_color_convert(
            input_path="input.exr",
            output_path="output.exr",
            config_path="config.ocio",
            source_colorspace=None,
            source_display="sRGB - Display",
            source_view="ACES 1.0 - SDR Video",
            target_colorspace="Rec.1886 Rec.709 - Display",
        )

        cmd = self._get_oiio_cmd()

        self.assertIn(
            "--ociodisplay:from=Rec.1886 Rec.709 - Display"
            ":inverse=1:subimages=0",
            cmd,
        )

    def test_display_view_to_different_display_view_is_two_step(self):
        oiio_color_convert(
            input_path="input.exr",
            output_path="output.exr",
            config_path="config.ocio",
            source_colorspace=None,
            source_display="sRGB - Display",
            source_view="ACES 1.0 - SDR Video",
            target_display="Rec.1886 Rec.709 - Display",
            target_view="ACES 1.0 - SDR Video",
        )

        cmd = self._get_oiio_cmd()

        inverse_idx = cmd.index("--ociodisplay:inverse=1:subimages=0")
        self.assertEqual(cmd[inverse_idx + 1], "sRGB - Display")
        self.assertEqual(cmd[inverse_idx + 2], "ACES 1.0 - SDR Video")

        forward_idx = cmd.index("--ociodisplay:subimages=0")
        self.assertEqual(
            cmd[forward_idx + 1], "Rec.1886 Rec.709 - Display"
        )
        self.assertEqual(cmd[forward_idx + 2], "ACES 1.0 - SDR Video")

        # Inverse must be applied before the forward conversion.
        self.assertLess(inverse_idx, forward_idx)

        self.assertFalse(
            any(arg.startswith("--colorconvert") for arg in cmd)
        )

    def test_display_view_to_same_display_view_needs_no_conversion(self):
        oiio_color_convert(
            input_path="input.exr",
            output_path="output.exr",
            config_path="config.ocio",
            source_colorspace=None,
            source_display="sRGB - Display",
            source_view="ACES 1.0 - SDR Video",
            target_display="sRGB - Display",
            target_view="ACES 1.0 - SDR Video",
        )

        cmd = self._get_oiio_cmd()

        self.assertFalse(
            any(
                arg.startswith("--ociodisplay")
                or arg.startswith("--colorconvert")
                for arg in cmd
            )
        )
