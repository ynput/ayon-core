"""Tests for the representation traits."""
from __future__ import annotations

from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    FileLocation,
    Image,
    PixelBased,
    Planar,
    TraitBase,
    TraitsData,
)

TRAITS_DATA = {
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
def traits_data() -> TraitsData:
    """Return a traits data instance."""
    return TraitsData(traits=[
        FileLocation(**TRAITS_DATA[FileLocation.id]),
        Image(),
        PixelBased(**TRAITS_DATA[PixelBased.id]),
        Planar(**TRAITS_DATA[Planar.id]),
    ])

def test_traits_data(traits_data: TraitsData) -> None:
    """Test setting and getting traits."""
    assert len(traits_data) == len(TRAITS_DATA)
    assert traits_data.get(trait_id=FileLocation.id)
    assert traits_data.get(trait_id=Image.id)
    assert traits_data.get(trait_id=PixelBased.id)
    assert traits_data.get(trait_id=Planar.id)

    assert traits_data.get(trait=FileLocation)
    assert traits_data.get(trait=Image)
    assert traits_data.get(trait=PixelBased)
    assert traits_data.get(trait=Planar)

    assert issubclass(type(traits_data.get(trait=FileLocation)), TraitBase)

    assert traits_data.get(
        trait=FileLocation) == traits_data.get(trait_id=FileLocation.id)
    assert traits_data.get(
        trait=Image) == traits_data.get(trait_id=Image.id)
    assert traits_data.get(
        trait=PixelBased) == traits_data.get(trait_id=PixelBased.id)
    assert traits_data.get(
        trait=Planar) == traits_data.get(trait_id=Planar.id)

    assert traits_data.get(trait_id="ayon.2d.Image.v1")
    assert traits_data.get(trait_id="ayon.2d.PixelBased.v1")
    assert traits_data.get(trait_id="ayon.2d.Planar.v1")

    assert traits_data.get(
        trait_id="ayon.2d.PixelBased.v1").display_window_width == \
           TRAITS_DATA[PixelBased.id]["display_window_width"]
    assert traits_data.get(
        trait=PixelBased).display_window_height == \
           TRAITS_DATA[PixelBased.id]["display_window_height"]


def test_traits_data_to_dict(traits_data: TraitsData) -> None:
    """Test converting traits data to dictionary."""
    result = traits_data.as_dict()
    assert result == TRAITS_DATA
