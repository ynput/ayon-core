"""Tests for the time related traits."""
from __future__ import annotations

from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    FrameRanged,
    Handles,
    Representation,
    Sequence,
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
            frame_end=1100, frames_per_second="25"),
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
            frame_end=1100, frames_per_second="25"),
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
            frame_end=1100, frames_per_second="25"),
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
                frame_end=1050, frames_per_second="25"),
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
            frame_end=1050, frames_per_second="25"),
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
            match="Invalid frame number in the list: .*"):
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

