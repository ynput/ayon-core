"""Tests for the content traits."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    PixelBased,
    Planar,
    Representation,
    Sequence,
)
from ayon_core.pipeline.traits.trait import TraitValidationError


def test_bundles() -> None:
    """Test bundle trait."""
    diffuse_texture = [
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
        FileLocation(
            file_path=Path("/path/to/diffuse.jpg"),
            file_size=1024,
            file_hash=None),
        MimeType(mime_type="image/jpeg"),
    ]
    bump_texture = [
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
        FileLocation(
            file_path=Path("/path/to/bump.tif"),
            file_size=1024,
            file_hash=None),
        MimeType(mime_type="image/tiff"),
    ]
    bundle = Bundle(items=[diffuse_texture, bump_texture])
    representation = Representation(name="test_bundle", traits=[bundle])

    if representation.contains_trait(trait=Bundle):
        assert representation.get_trait(trait=Bundle).items == [
            diffuse_texture, bump_texture
        ]

    for item in representation.get_trait(trait=Bundle).items:
        sub_representation = Representation(name="test", traits=item)
        assert sub_representation.contains_trait(trait=Image)
        sub: MimeType = sub_representation.get_trait(trait=MimeType)
        assert sub.mime_type in {
            "image/jpeg", "image/tiff"
        }


def test_file_locations_validation() -> None:
    """Test FileLocations trait validation."""
    file_locations_list = [
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1051)
    ]

    representation = Representation(name="test", traits=[
        FileLocations(file_paths=file_locations_list),
        Sequence(frame_padding=4),
    ])

    file_locations_trait: FileLocations = FileLocations(
        file_paths=file_locations_list)

    # this should be valid trait
    file_locations_trait.validate_trait(representation)

    # add valid FrameRanged trait
    frameranged_trait = FrameRanged(
        frame_start=1001,
        frame_end=1050,
        frames_per_second="25"
    )
    representation.add_trait(frameranged_trait)

    # it should still validate fine
    file_locations_trait.validate_trait(representation)

    # create empty file locations trait
    empty_file_locations_trait = FileLocations(file_paths=[])
    representation = Representation(name="test", traits=[
        empty_file_locations_trait
    ])
    with pytest.raises(TraitValidationError):
        empty_file_locations_trait.validate_trait(representation)

    # create valid file locations trait but with not matching
    # frame range trait
    representation = Representation(name="test", traits=[
        FileLocations(file_paths=file_locations_list),
        Sequence(frame_padding=4),
    ])
    invalid_sequence_trait = FrameRanged(
        frame_start=1001,
        frame_end=1051,
        frames_per_second="25"
    )

    representation.add_trait(invalid_sequence_trait)
    with pytest.raises(TraitValidationError):
        file_locations_trait.validate_trait(representation)

    # invalid representation with multiple file locations but
    # unrelated to either Sequence or Bundle traits
    representation = Representation(name="test", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path("/path/to/file_foo.exr"),
                file_size=1024,
                file_hash=None,
            ),
            FileLocation(
                file_path=Path("/path/to/anotherfile.obj"),
                file_size=1234,
                file_hash=None,
            )
        ])
    ])

    with pytest.raises(TraitValidationError):
        representation.validate()


def test_get_file_location_from_frame() -> None:
    """Test get_file_location_from_frame method."""
    file_locations_list = [
        FileLocation(
            file_path=Path(f"/path/to/file.{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1051)
    ]

    file_locations_trait: FileLocations = FileLocations(
        file_paths=file_locations_list)

    assert file_locations_trait.get_file_location_for_frame(frame=1001) == \
        file_locations_list[0]
    assert file_locations_trait.get_file_location_for_frame(frame=1050) == \
        file_locations_list[-1]
    assert file_locations_trait.get_file_location_for_frame(frame=1100) is None

    # test with custom regex
    sequence = Sequence(
        frame_padding=4,
        frame_regex=re.compile(r"boo_(?P<index>(?P<padding>0*)\d+)\.exr"))
    file_locations_list = [
        FileLocation(
            file_path=Path(f"/path/to/boo_{frame}.exr"),
            file_size=1024,
            file_hash=None,
        )
        for frame in range(1001, 1051)
    ]

    file_locations_trait = FileLocations(
        file_paths=file_locations_list)

    assert file_locations_trait.get_file_location_for_frame(
        frame=1001, sequence_trait=sequence) == \
            file_locations_list[0]
