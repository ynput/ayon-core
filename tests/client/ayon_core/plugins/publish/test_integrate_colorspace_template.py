"""Tests for the colorspace template value of the integrator."""
import pytest

from ayon_core.plugins.publish.integrate import (
    get_colorspace_template_value,
)


@pytest.mark.parametrize(
    "colorspace_data, expected",
    [
        (None, None),
        ({}, None),
        ({"colorspace": "ACES - ACEScg"}, "ACES_-_ACEScg"),
        ({"colorspace": "sRGB", "display": "sRGB", "view": "Raw"}, "sRGB"),
        # display and view are not a colorspace
        ({"display": "sRGB", "view": "ACES 1.0 - SDR Video"}, None),
        ({"view": "Raw"}, None),
        ({"display": "sRGB"}, None),
        ({"colorspace": ""}, None),
        ({"config": {"path": "config.ocio"}}, None),
    ],
)
def test_get_colorspace_template_value(colorspace_data, expected):
    assert get_colorspace_template_value(colorspace_data) == expected
