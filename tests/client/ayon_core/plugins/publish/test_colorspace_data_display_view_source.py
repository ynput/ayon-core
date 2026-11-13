"""Publish plugins must accept display/view only representation colorspace."""

from __future__ import annotations

from unittest import mock

import pytest

from ayon_core.plugins.publish import extract_color_transcode
from ayon_core.plugins.publish.extract_color_transcode import (
    ExtractOIIOTranscode,
)
from ayon_core.plugins.publish.extract_thumbnail import (
    ExtractThumbnail,
    ThumbnailDef,
)

DISPLAY_VIEW = {"display": "sRGB", "view": "ACES 1.0 - SDR Video"}


@pytest.mark.parametrize(
    "colorspace_data, expected",
    [
        (
            {"colorspace": "ACES - ACEScg"},
            ("ACES - ACEScg", None, None),
        ),
        (dict(DISPLAY_VIEW), (None, "sRGB", "ACES 1.0 - SDR Video")),
        # All three: the display and view are the source
        (
            {"colorspace": "ACES - ACEScg", **DISPLAY_VIEW},
            (None, "sRGB", "ACES 1.0 - SDR Video"),
        ),
        # Only the config: reaches the new guard and is skipped
        ({"config": {"path": "config.ocio"}}, None),
        ({"config": {"path": "config.ocio"}, "display": "sRGB"}, None),
        ({"config": {"path": "config.ocio"}, "view": "Raw"}, None),
        # A colorspace with a single display: the colorspace is the source
        (
            {"colorspace": "ACES - ACEScg", "display": "sRGB"},
            ("ACES - ACEScg", None, None),
        ),
    ],
)
def test_transcode_source(colorspace_data, expected):
    plugin = ExtractOIIOTranscode()
    output_def = {
        "name": "out",
        "extension": "jpg",
        "transcoding_type": "colorspace",
        "colorspace": "sRGB",
        "oiiotool_args": {"additional_command_args": []},
        "tags": [],
    }
    profile = {
        "outputs": [output_def],
        "delete_original": False,
        "representation_names": [],
    }
    repre = {
        "name": "exr",
        "ext": "exr",
        "files": "file.exr",
        "stagingDir": "/staging",
        "colorspaceData": colorspace_data,
    }
    instance = mock.MagicMock()
    instance.data = {"representations": [repre], "families": []}
    instance.context.data = {
        "hostName": "nuke",
        "projectName": "project",
        "project_settings": {},
        "cleanupFullPaths": [],
        "anatomy": mock.MagicMock(),
    }
    plugin.profiles = [profile]
    module = extract_color_transcode
    with (
        mock.patch.object(module, "is_oiio_supported", return_value=True),
        mock.patch.object(plugin, "_get_profile", return_value=profile),
        mock.patch.object(
            module, "get_default_reviewable_layers", return_value=[]
        ),
        mock.patch.object(
            module,
            "get_representation_ocio_config_path",
            return_value="config.ocio",
        ),
        mock.patch.object(module, "get_temp_dir", return_value="/tmp/out"),
        mock.patch.object(module, "oiio_color_convert") as convert,
    ):
        plugin.process(instance)

    if expected is None:
        convert.assert_not_called()
        return
    convert.assert_called_once()
    kwargs = convert.call_args.kwargs
    assert (
        kwargs["source_colorspace"],
        kwargs["source_display"],
        kwargs["source_view"],
    ) == expected


@pytest.mark.parametrize(
    "colorspace_data, expected",
    [
        (
            {"colorspace": "ACES - ACEScg"},
            ("ACES - ACEScg", None, None),
        ),
        (dict(DISPLAY_VIEW), (None, "sRGB", "ACES 1.0 - SDR Video")),
        (
            {"colorspace": "ACES - ACEScg", **DISPLAY_VIEW},
            (None, "sRGB", "ACES 1.0 - SDR Video"),
        ),
        # A single display is not paired with a default view
        (
            {"colorspace": "ACES - ACEScg", "display": "sRGB"},
            ("ACES - ACEScg", None, None),
        ),
        ({}, None),
    ],
)
def test_thumbnail_source(colorspace_data, expected):
    from ayon_core.plugins.publish import extract_thumbnail as module

    plugin = ExtractThumbnail()
    repre = {"colorspaceData": colorspace_data}
    with (
        mock.patch.object(
            module,
            "get_representation_ocio_config_path",
            return_value="config.ocio",
        ),
        mock.patch.object(module, "oiio_color_convert") as convert,
        mock.patch.object(plugin, "_get_resolution_args", return_value=[]),
    ):
        result = plugin._create_colorspace_thumbnail(
            "src.exr", "dst.jpg", repre, ThumbnailDef(), mock.MagicMock(), []
        )

    if expected is None:
        assert result is False
        convert.assert_not_called()
        return
    assert result is True
    args = convert.call_args.args
    kwargs = convert.call_args.kwargs
    assert (
        args[3],
        kwargs["source_display"],
        kwargs["source_view"],
    ) == expected
    # The target is the display and view of the representation when both
    #   are set, else the thumbnail defaults (none here)
    assert (kwargs["target_display"], kwargs["target_view"]) == (
        expected[1],
        expected[2],
    )
