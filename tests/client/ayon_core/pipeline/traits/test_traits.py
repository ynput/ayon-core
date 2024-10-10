"""Tests for the representation traits."""
from __future__ import annotations

from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    Image,
    PixelBased,
    Planar,
    Representation,
    TraitBase,
)

REPRESENTATION_DATA = {
        FileLocation.id: {
            "file_path": Path("/path/to/file"),
            "file_size": 1024,
            "file_hash": None,
        },
        Image.id: {},
        PixelBased.id: {
            "display_window_width": 1920,
            "display_window_height": 1080,
            "pixel_aspect_ratio": 1.0,
        },
        Planar.id: {
            "planar_configuration": "RGB",
        },
    }


@pytest.fixture()
def representation() -> Representation:
    """Return a traits data instance."""
    return Representation(traits=[
        FileLocation(**REPRESENTATION_DATA[FileLocation.id]),
        Image(),
        PixelBased(**REPRESENTATION_DATA[PixelBased.id]),
        Planar(**REPRESENTATION_DATA[Planar.id]),
    ])

def test_representation_traits(representation: Representation) -> None:
    """Test setting and getting traits."""
    assert len(representation) == len(REPRESENTATION_DATA)
    assert representation.get_trait(trait_id=FileLocation.id)
    assert representation.get_trait(trait_id=Image.id)
    assert representation.get_trait(trait_id=PixelBased.id)
    assert representation.get_trait(trait_id=Planar.id)

    assert representation.get_trait(trait=FileLocation)
    assert representation.get_trait(trait=Image)
    assert representation.get_trait(trait=PixelBased)
    assert representation.get_trait(trait=Planar)

    assert issubclass(
        type(representation.get_trait(trait=FileLocation)), TraitBase)

    assert representation.get_trait(
        trait=FileLocation) == representation.get_trait(
            trait_id=FileLocation.id)
    assert representation.get_trait(
        trait=Image) == representation.get_trait(
            trait_id=Image.id)
    assert representation.get_trait(
        trait=PixelBased) == representation.get_trait(
            trait_id=PixelBased.id)
    assert representation.get_trait(
        trait=Planar) == representation.get_trait(
            trait_id=Planar.id)

    assert representation.get_trait(trait_id="ayon.2d.Image.v1")
    assert representation.get_trait(trait_id="ayon.2d.PixelBased.v1")
    assert representation.get_trait(trait_id="ayon.2d.Planar.v1")

    assert representation.get_trait(
        trait_id="ayon.2d.PixelBased.v1").display_window_width == \
           REPRESENTATION_DATA[PixelBased.id]["display_window_width"]
    assert representation.get_trait(
        trait=PixelBased).display_window_height == \
           REPRESENTATION_DATA[PixelBased.id]["display_window_height"]

def test_getting_traits_data(representation: Representation) -> None:
    """Test getting a batch of traits."""
    result = representation.get_traits(
        trait_ids=[FileLocation.id, Image.id, PixelBased.id, Planar.id])
    assert result == {
         "ayon.2d.Image.v1": Image(),
         "ayon.2d.PixelBased.v1": PixelBased(
             display_window_width=1920,
             display_window_height=1080,
             pixel_aspect_ratio=1.0),
         "ayon.2d.Planar.v1": Planar(planar_configuration="RGB"),
         "ayon.content.FileLocation.v1": FileLocation(
             file_path=Path("/path/to/file"),
             file_size=1024,
             file_hash=None)
    }


def test_traits_data_to_dict(representation: Representation) -> None:
    """Test converting traits data to dictionary."""
    result = representation.traits_as_dict()
    assert result == REPRESENTATION_DATA
