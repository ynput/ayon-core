"""Tests for the 2d related traits."""
from __future__ import annotations

from pathlib import Path

from ayon_core.pipeline.traits import (
    UDIM,
    FileLocation,
    FileLocations,
    Representation,
)


def test_get_file_location_for_udim() -> None:
    """Test get_file_location_for_udim."""
    file_locations_list = [
        FileLocation(
            file_path=Path("/path/to/file.1001.exr"),
            file_size=1024,
            file_hash=None,
        ),
        FileLocation(
            file_path=Path("/path/to/file.1002.exr"),
            file_size=1024,
            file_hash=None,
        ),
        FileLocation(
            file_path=Path("/path/to/file.1003.exr"),
            file_size=1024,
            file_hash=None,
        ),
    ]

    representation = Representation(name="test_1", traits=[
        FileLocations(file_paths=file_locations_list),
        UDIM(udim=[1001, 1002, 1003]),
    ])

    udim_trait = representation.get_trait(UDIM)
    assert udim_trait.get_file_location_for_udim(
        file_locations=representation.get_trait(FileLocations),
        udim=1001
    ) == file_locations_list[0]

def test_get_udim_from_file_location() -> None:
    """Test get_udim_from_file_location."""
    file_location_1 = FileLocation(
        file_path=Path("/path/to/file.1001.exr"),
        file_size=1024,
        file_hash=None,
    )

    file_location_2 = FileLocation(
        file_path=Path("/path/to/file.xxxxx.exr"),
        file_size=1024,
        file_hash=None,
    )
    assert UDIM(udim=[1001]).get_udim_from_file_location(
        file_location_1) == 1001

    assert UDIM(udim=[1001]).get_udim_from_file_location(
        file_location_2) is None
