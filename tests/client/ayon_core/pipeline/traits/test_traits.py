"""Tests for the representation traits."""
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
    Overscan,
    PixelBased,
    Planar,
    Representation,
    Sequence,
    TraitBase,
)
from ayon_core.pipeline.traits.trait import TraitValidationError

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

class UpgradedImage(Image):
    """Upgraded image class."""
    id = "ayon.2d.Image.v2"

    @classmethod
    def upgrade(cls, data: dict) -> UpgradedImage:  # noqa: ARG003
        """Upgrade the trait."""
        return cls()

class InvalidTrait:
    """Invalid trait class."""
    foo = "bar"

@pytest.fixture()
def representation() -> Representation:
    """Return a traits data instance."""
    return Representation(name="test", traits=[
        FileLocation(**REPRESENTATION_DATA[FileLocation.id]),
        Image(),
        PixelBased(**REPRESENTATION_DATA[PixelBased.id]),
        Planar(**REPRESENTATION_DATA[Planar.id]),
    ])

def test_representation_errors(representation: Representation) -> None:
    """Test errors in representation."""
    with pytest.raises(ValueError,
                       match="Invalid trait .* - ID is required."):
        representation.add_trait(InvalidTrait())

    with pytest.raises(ValueError,
                       match=f"Trait with ID {Image.id} already exists."):
        representation.add_trait(Image())

    with pytest.raises(ValueError,
                       match="Trait with ID .* not found."):
        representation.remove_trait_by_id("foo")

def test_representation_traits(representation: Representation) -> None:
    """Test setting and getting traits."""
    assert representation.get_trait_by_id(
        "ayon.2d.PixelBased").get_version() == 1

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
    empty_representation = Representation(name="test", traits=[])
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

def test_get_version_from_id() -> None:
    """Test getting version from trait ID."""
    assert Image().get_version() == 1

    class TestOverscan(Overscan):
        id = "ayon.2d.Overscan.v2"

    assert TestOverscan(
        left=0,
        right=0,
        top=0,
        bottom=0
    ).get_version() == 2

    class TestMimeType(MimeType):
        id = "ayon.content.MimeType"

    assert TestMimeType(mime_type="foo/bar").get_version() is None

def test_get_versionless_id() -> None:
    """Test getting versionless trait ID."""
    assert Image().get_versionless_id() == "ayon.2d.Image"

    class TestOverscan(Overscan):
        id = "ayon.2d.Overscan.v2"

    assert TestOverscan(
        left=0,
        right=0,
        top=0,
        bottom=0
    ).get_versionless_id() == "ayon.2d.Overscan"

    class TestMimeType(MimeType):
        id = "ayon.content.MimeType"

    assert TestMimeType(mime_type="foo/bar").get_versionless_id() == \
           "ayon.content.MimeType"


def test_from_dict() -> None:
    """Test creating representation from dictionary."""
    traits_data = {
        "ayon.content.FileLocation.v1": {
            "file_path": "/path/to/file",
            "file_size": 1024,
            "file_hash": None,
        },
        "ayon.2d.Image.v1": {},
    }

    representation = Representation.from_dict(
        "test", trait_data=traits_data)

    assert len(representation) == 2
    assert representation.get_trait_by_id("ayon.content.FileLocation.v1")
    assert representation.get_trait_by_id("ayon.2d.Image.v1")

    traits_data = {
        "ayon.content.FileLocation.v999": {
            "file_path": "/path/to/file",
            "file_size": 1024,
            "file_hash": None,
        },
    }

    with pytest.raises(ValueError, match="Trait model with ID .* not found."):
        representation = Representation.from_dict(
            "test", trait_data=traits_data)

    traits_data = {
        "ayon.content.FileLocation": {
            "file_path": "/path/to/file",
            "file_size": 1024,
            "file_hash": None,
        },
    }

    representation = Representation.from_dict(
        "test", trait_data=traits_data)

    assert len(representation) == 1
    assert representation.get_trait_by_id("ayon.content.FileLocation.v1")

    # this won't work right now because we would need to somewhat mock
    # the import
    """
    from .lib import NewTestTrait

    traits_data = {
        "ayon.test.NewTestTrait.v1": {},
    }

    representation = Representation.from_dict(
        "test", trait_data=traits_data)
    """

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
        frame_padding=4,
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
        frame_padding=4,
        frames_per_second="25"
    )

    representation.add_trait(invalid_sequence_trait)
    with pytest.raises(TraitValidationError):
        file_locations_trait.validate(representation)
