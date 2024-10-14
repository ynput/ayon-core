"""Tests for the representation traits."""
from __future__ import annotations

from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocation,
    Image,
    MimeType,
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

def test_representation_errors(representation: Representation) -> None:
    """Test errors in representation."""
    with pytest.raises(ValueError,
                       match="Trait ID or Trait class is required"):
        representation.get_trait()

    with pytest.raises(ValueError,
                       match="Trait ID or Trait class is required"):
        representation.contains_trait()

def test_representation_traits(representation: Representation) -> None:
    """Test setting and getting traits."""
    assert len(representation) == len(REPRESENTATION_DATA)
    assert representation.get_trait_by_id(FileLocation.id)
    assert representation.get_trait_by_id(Image.id)
    assert representation.get_trait_by_id(trait_id="ayon.2d.Image.v1")
    assert representation.get_trait_by_id(PixelBased.id)
    assert representation.get_trait_by_id(trait_id="ayon.2d.PixelBased.v1")
    assert representation.get_trait_by_id(Planar.id)
    assert representation.get_trait_by_id(trait_id="ayon.2d.Planar.v1")

    assert representation.get_trait(FileLocation)
    assert representation.get_trait(Image)
    assert representation.get_trait(PixelBased)
    assert representation.get_trait(Planar)

    assert issubclass(
        type(representation.get_trait(FileLocation)), TraitBase)

    assert representation.get_trait(FileLocation) == \
           representation.get_trait_by_id(FileLocation.id)
    assert representation.get_trait(Image) == \
           representation.get_trait_by_id(Image.id)
    assert representation.get_trait(PixelBased) == \
           representation.get_trait_by_id(PixelBased.id)
    assert representation.get_trait(Planar) == \
           representation.get_trait_by_id(Planar.id)

    assert representation.get_trait_by_id(
        "ayon.2d.PixelBased.v1").display_window_width == \
           REPRESENTATION_DATA[PixelBased.id]["display_window_width"]
    assert representation.get_trait(
        trait=PixelBased).display_window_height == \
           REPRESENTATION_DATA[PixelBased.id]["display_window_height"]

    repre_dict = {
        FileLocation.id: FileLocation(**REPRESENTATION_DATA[FileLocation.id]),
        Image.id: Image(),
        PixelBased.id: PixelBased(**REPRESENTATION_DATA[PixelBased.id]),
        Planar.id: Planar(**REPRESENTATION_DATA[Planar.id]),
    }
    assert representation.get_traits() == repre_dict

    assert representation.get_traits_by_ids(
        trait_ids=[FileLocation.id, Image.id, PixelBased.id, Planar.id]) == \
           repre_dict
    assert representation.get_traits(
        [FileLocation, Image, PixelBased, Planar]) == \
              repre_dict

    assert representation.has_traits() is True
    empty_representation = Representation(traits=[])
    assert empty_representation.has_traits() is False

    assert representation.contains_trait(trait=FileLocation) is True
    assert representation.contains_traits([Image, FileLocation]) is True
    assert representation.contains_trait_by_id(FileLocation.id) is True
    assert representation.contains_traits_by_id(
        trait_ids=[FileLocation.id, Image.id]) is True

    assert representation.contains_trait(trait=Bundle) is False
    assert representation.contains_traits([Image, Bundle]) is False
    assert representation.contains_trait_by_id(Bundle.id) is False
    assert representation.contains_traits_by_id(
        trait_ids=[FileLocation.id, Bundle.id]) is False

def test_trait_removing(representation: Representation) -> None:
    """Test removing traits."""
    assert  representation.contains_trait_by_id("nonexistent") is False
    with pytest.raises(
            ValueError, match="Trait with ID nonexistent not found."):
        representation.remove_trait_by_id("nonexistent")

    assert representation.contains_trait(trait=FileLocation) is True
    representation.remove_trait(trait=FileLocation)
    assert representation.contains_trait(trait=FileLocation) is False

    assert representation.contains_trait_by_id(Image.id) is True
    representation.remove_trait_by_id(Image.id)
    assert representation.contains_trait_by_id(Image.id) is False

    assert representation.contains_traits([PixelBased, Planar]) is True
    representation.remove_traits([Planar, PixelBased])
    assert representation.contains_traits([PixelBased, Planar]) is False

    assert representation.has_traits() is False

    with pytest.raises(
            ValueError, match=f"Trait with ID {Image.id} not found."):
        representation.remove_trait(Image)


def test_getting_traits_data(representation: Representation) -> None:
    """Test getting a batch of traits."""
    result = representation.get_traits_by_ids(
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
    representation = Representation(traits=[bundle])

    if representation.contains_trait(trait=Bundle):
        assert representation.get_trait(trait=Bundle).items == [
            diffuse_texture, bump_texture
        ]

    for item in representation.get_trait(trait=Bundle).items:
        sub_representation = Representation(traits=item)
        assert sub_representation.contains_trait(trait=Image)
        assert sub_representation.get_trait(trait=MimeType).mime_type in [
            "image/jpeg", "image/tiff"
        ]
