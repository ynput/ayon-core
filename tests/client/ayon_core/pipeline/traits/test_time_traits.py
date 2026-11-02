"""Tests for the time related traits."""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    FrameRanged,
    Handles,
    Representation,
    Sequence,
    parse_frame_rate,
)
from ayon_core.pipeline.traits.trait import TraitValidationError


def test_sequence_validations() -> None:
    """Test Sequence trait validation."""
    file_locations_list = [
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1010 + 1)  # because range is zero based
    ]

    file_locations_list += [
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1015, 1020 + 1)
    ]

    file_locations_list += [
        FileLocation
        (
            file_path=Path("/path/to/file.1100.exr"),
            file_size=1024,
            file_hash=None,
        )
    ]

    representation = Representation(name="test_1", traits=[
        FileLocations(file_paths=file_locations_list),
        FrameRanged(
            frame_start=1001,
            frame_end=1100, frame_rate_numerator=25),
        Sequence(
            frame_padding=4,
            frame_spec="1001-1010,1015-1020,1100")
    ])

    representation.get_trait(Sequence).validate_trait(representation)

    # here we set handles and set them as inclusive, so this should pass
    representation = Representation(name="test_2", traits=[
        FileLocations(file_paths=[
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1100 + 1)  # because range is zero based
    ]),
        Handles(
            frame_start_handle=5,
            frame_end_handle=5,
            inclusive=True
        ),
        FrameRanged(
            frame_start=1001,
            frame_end=1100, frame_rate_numerator=25),
        Sequence(frame_padding=4)
    ])

    representation.validate()

    # do the same but set handles as exclusive
    representation = Representation(name="test_3", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(996, 1105 + 1)  # because range is zero based
        ]),
        Handles(
            frame_start_handle=5,
            frame_end_handle=5,
            inclusive=False
        ),
        FrameRanged(
            frame_start=1001,
            frame_end=1100, frame_rate_numerator=25),
        Sequence(frame_padding=4)
    ])

    representation.validate()

    # invalid representation with file range not extended for handles
    representation = Representation(name="test_4", traits=[
            FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(1001, 1050 + 1)  # because range is zero based
        ]),
            Handles(
                frame_start_handle=5,
                frame_end_handle=5,
                inclusive=False
            ),
            FrameRanged(
                frame_start=1001,
                frame_end=1050, frame_rate_numerator=25),
            Sequence(frame_padding=4)
        ])

    with pytest.raises(TraitValidationError):
        representation.validate()

    # invalid representation with frame spec not matching the files
    del representation
    representation = Representation(name="test_5", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(1001, 1050 + 1)  # because range is zero based
        ]),
        FrameRanged(
            frame_start=1001,
            frame_end=1050, frame_rate_numerator=25),
        Sequence(frame_padding=4, frame_spec="1001-1010,1012-2000")
    ])
    with pytest.raises(TraitValidationError):
        representation.validate()

    representation = Representation(name="test_6", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(1001, 1050 + 1)  # because range is zero based
        ]),
        Sequence(frame_padding=4, frame_spec="1-1010,1012-1050"),
        Handles(
            frame_start_handle=5,
            frame_end_handle=5,
            inclusive=False
        )
    ])
    with pytest.raises(TraitValidationError):
        representation.validate()

    representation = Representation(name="test_6", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(996, 1050 + 1)  # because range is zero based
        ]),
        Sequence(frame_padding=4, frame_spec="1001-1010,1012-2000"),
        Handles(
            frame_start_handle=5,
            frame_end_handle=5,
            inclusive=False
        )
    ])
    with pytest.raises(TraitValidationError):
        representation.validate()

    representation = Representation(name="test_7", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/file.{frame}.exr"),
                file_size=1024,
                file_hash=None,
            )
            for frame in range(996, 1050 + 1)  # because range is zero based
        ]),
        Sequence(
            frame_padding=4,
            frame_regex=re.compile(
                    r"img\.(?P<index>(?P<padding>0*)\d{4})\.png$")),
        Handles(
            frame_start_handle=5,
            frame_end_handle=5,
            inclusive=False
        )
    ])
    representation.validate()


def test_list_spec_to_frames() -> None:
    """Test converting list specification to frames."""
    assert Sequence.list_spec_to_frames("1-10,20-30,55") == [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
        20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 55
    ]
    assert Sequence.list_spec_to_frames("1,2,3,4,5") == [
        1, 2, 3, 4, 5
    ]
    assert Sequence.list_spec_to_frames("1-10") == [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    ]
    test_list = list(range(1001, 1011))
    test_list += list(range(1012, 2001))
    assert Sequence.list_spec_to_frames("1001-1010,1012-2000") == test_list

    assert Sequence.list_spec_to_frames("1") == [1]
    with pytest.raises(
            ValueError,
            match=r"Invalid frame number in the list: .*"):
        Sequence.list_spec_to_frames("a")


def test_sequence_get_frame_padding() -> None:
    """Test getting frame padding from FileLocations trait."""
    file_locations_list = [
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1051)
    ]

    representation = Representation(name="test", traits=[
        FileLocations(file_paths=file_locations_list)
    ])

    assert Sequence.get_frame_padding(
        file_locations=representation.get_trait(FileLocations)) == 4


@pytest.mark.parametrize(("value", "expected"), [
    (25, Fraction(25)),
    ("25", Fraction(25)),
    (25.0, Fraction(25)),
    ("24000/1001", Fraction(24000, 1001)),
    (Fraction(48, 2), Fraction(24)),
    # decimal NTSC frame rates
    (23.976, Fraction(24000, 1001)),
    ("29.97", Fraction(30000, 1001)),
    (59.94, Fraction(60000, 1001)),
    (12.5, Fraction(25, 2)),
    (None, None),
    ("", None),
])
def test_parse_frame_rate(value, expected) -> None:
    """Frame rate is converted to reduced exact fraction."""
    assert parse_frame_rate(value) == expected


def test_frame_rate() -> None:
    """Frame rate is stored as reduced fraction."""
    frame_ranged = FrameRanged(frame_start=1001, frame_end=1100)
    assert frame_ranged.frame_rate is None

    frame_ranged.frame_rate = "48/2"
    assert frame_ranged.frame_rate_numerator == 24
    assert frame_ranged.frame_rate_denominator == 1

    frame_ranged.frame_rate = 29.97
    assert frame_ranged.frame_rate == Fraction(30000, 1001)

    with pytest.raises(ValueError):
        frame_ranged.frame_rate = 0


@pytest.mark.parametrize(("value", "precision", "expected"), [
    (None, None, ""),
    (None, 3, ""),
    (25, None, "25"),
    (25, 3, "25.000"),
    (12.5, None, "12.5"),
    (Fraction(24000, 1001), None, "23.976023976023978"),
    (Fraction(24000, 1001), 3, "23.976"),
    (Fraction(24000, 1001), 2, "23.98"),
    (Fraction(24000, 1001), 0, "24"),
])
def test_get_fps_string(value, precision, expected) -> None:
    """Frame rate strings support optional fixed decimal precision."""
    frame_ranged = FrameRanged(frame_start=1001, frame_end=1100)
    frame_ranged.frame_rate = value

    assert frame_ranged.get_fps_string(precision) == expected
    if precision is None:
        assert frame_ranged.get_fps_string() == expected


def test_frame_ranged_upgrade() -> None:
    """Version 1 data with string frame rate are upgraded."""
    representation = Representation.from_dict("test", trait_data={
        "ayon.time.FrameRanged.v1": {
            "frame_start": 1001,
            "frame_end": 1100,
            "frames_per_second": "23.976",
        },
    })

    frame_ranged = representation.get_trait(FrameRanged)
    assert frame_ranged.id == "ayon.time.FrameRanged.v2"
    assert (frame_ranged.frame_start, frame_ranged.frame_end) == (1001, 1100)
    assert frame_ranged.frame_rate == Fraction(24000, 1001)
    assert "frames_per_second" not in frame_ranged.as_dict()
