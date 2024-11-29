"""Tests for the content traits."""
from __future__ import annotations

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
        assert sub_representation.get_trait(trait=MimeType).mime_type in [
            "image/jpeg", "image/tiff"
        ]


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
        FileLocations(file_paths=file_locations_list)
    ])

    file_locations_trait: FileLocations = FileLocations(
        file_paths=file_locations_list)

    # this should be valid trait
    file_locations_trait.validate(representation)

    # add valid FrameRanged trait
    sequence_trait = FrameRanged(
        frame_start=1001,
        frame_end=1050,
        frames_per_second="25"
    )
    representation.add_trait(sequence_trait)

     # it should still validate fine
    file_locations_trait.validate(representation)

    # create empty file locations trait
    empty_file_locations_trait = FileLocations(file_paths=[])
    representation = Representation(name="test", traits=[
        empty_file_locations_trait
    ])
    with pytest.raises(TraitValidationError):
        empty_file_locations_trait.validate(representation)

    # create valid file locations trait but with not matching sequence
    # trait
    representation = Representation(name="test", traits=[
        FileLocations(file_paths=file_locations_list)
    ])
    invalid_sequence_trait = FrameRanged(
        frame_start=1001,
        frame_end=1051,
        frames_per_second="25"
    )

    representation.add_trait(invalid_sequence_trait)
    with pytest.raises(TraitValidationError):
        file_locations_trait.validate(representation)

