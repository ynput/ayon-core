"""Tests for overscan crop string parsing of ExtractReview plugin."""
from __future__ import annotations

import pytest

from ayon_core.plugins.publish.extract_review import OverscanCrop

INPUT_WIDTH = 2000
INPUT_HEIGHT = 1000


@pytest.mark.parametrize(
    "string_value, expected_size",
    [
        ("", (2000, 1000)),
        (None, (2000, 1000)),
        ("0", (2000, 1000)),
        ("0px", (2000, 1000)),
        ("0%", (2000, 1000)),
        ("10%", (200, 100)),
        ("-10%", (1800, 900)),
        ("+10%", (2200, 1100)),
        ("-10%+", (1818, 909)),
        ("300px", (300, 300)),
        ("300", (300, 300)),
        ("-300px", (1700, 700)),
        ("+300px", (2300, 1300)),
        ("- 300 px", (1700, 700)),
        ("10 %", (200, 100)),
        ("3072 1728", (3072, 1728)),
        ("3072px 1728px", (3072, 1728)),
        ("3072PX 1728", (3072, 1728)),
        ("+100px +120px", (2100, 1120)),
        ("-10% -200px", (1800, 800)),
        ("50% - 200", (1000, 800)),
        ("+100 -200", (2100, 800)),
        ("50% 300", (1000, 300)),
    ]
)
def test_overscan_crop_valid_string(
    string_value: str | None, expected_size: tuple[int, int]
) -> None:
    """Valid overscan strings are converted to expected output size."""
    overscan = OverscanCrop(INPUT_WIDTH, INPUT_HEIGHT, string_value)
    assert (overscan.width(), overscan.height()) == expected_size


@pytest.mark.parametrize(
    "string_value",
    [
        # Unknown suffix
        "3072p",
        "3072pix",
        "10percent",
        "10%%",
        # Relative source sign without relative value
        "10%+",
        "10%-",
        # Not a number
        "px",
        "abc",
        "+",
        "10.5%",
        # Too many values
        "100 200 300",
        "100px 200px 300px",
    ]
)
def test_overscan_crop_invalid_string(string_value: str) -> None:
    """Invalid overscan strings raise an error."""
    with pytest.raises(ValueError, match="Invalid string for rescaling"):
        OverscanCrop(INPUT_WIDTH, INPUT_HEIGHT, string_value)
