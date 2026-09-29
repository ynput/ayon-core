"""Tests for the representation traits."""
from __future__ import annotations

from pathlib import Path

import pytest
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocation,
    FileLocations,
    FrameRanged,
    GapPolicy,
    Image,
    MimeType,
    Overscan,
    PixelBased,
    Planar,
    Representation,
    Sequence,
    TraitBase,
)
from ayon_core.pipeline.traits.representation import (
    IncompatibleTraitVersionError
)

from typing import TypeVar

REPRESENTATION_DATA: dict = {
        FileLocation.id: {
            "file_path": Path("/path/to/file"),
            "file_size": 1024,
            "file_hash": None,
            # "persistent": True,
        },
        Image.id: {},
        PixelBased.id: {
            "display_window_width": 1920,
            "display_window_height": 1080,
            "pixel_aspect_ratio": 1.0,
            # "persistent": True,
        },
        Planar.id: {
            "planar_configuration": "RGB",
            # "persistent": True,
        },
    }

T = TypeVar("T", bound="TraitBase")


class UpgradedImage(Image):
    """Upgraded image class."""
    id = "ayon.2d.Image.v2"

    @classmethod
    def upgrade(cls, data: dict) -> UpgradedImage:  # noqa: ARG003
        """Upgrade the trait.

        Returns:
            UpgradedImage: Upgraded image instance.

        """
        return cls()


class InvalidTrait:
    """Invalid trait class."""
    foo = "bar"


@pytest.fixture
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
                       match=r"Invalid trait .* - ID is required."):
        representation.add_trait(InvalidTrait())

    with pytest.raises(ValueError,
                       match=f"Trait with ID {Image.id} already exists."):
        representation.add_trait(Image())

    with pytest.raises(ValueError,
                       match=r"Trait with ID .* not found."):
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
    empty_representation: Representation = Representation(
        name="test", traits=[])
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
    assert representation.contains_trait_by_id("nonexistent") is False
    with pytest.raises(
            ValueError, match=r"Trait with ID nonexistent not found."):
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


def test_representation_dict_properties(
        representation: Representation) -> None:
    """Test representation as dictionary."""
    representation = Representation(name="test")
    representation[Image.id] = Image()
    assert Image.id in representation
    image = representation[Image.id]
    assert image == Image()
    for trait_id, trait in representation.items():
        assert trait_id == Image.id
        assert trait == Image()


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


def test_get_trait_class_by_trait_id() -> None:
    """Test getting trait class by trait ID."""
    # this will return Image because the explicit version is requested
    trait_class = Representation.get_trait_class_by_trait_id(
        "ayon.2d.Image.v1")
    assert trait_class == Image

    # This will return UpgradedImage because the highest version is available,
    # and it is defined in the test
    trait_class = Representation.get_trait_class_by_trait_id("ayon.2d.Image")
    assert trait_class == UpgradedImage

    # These both will return FileLocation because only one version exists
    trait_class = Representation.get_trait_class_by_trait_id(
        "ayon.content.FileLocation.v1")
    assert trait_class == FileLocation

    trait_class = Representation.get_trait_class_by_trait_id(
        "ayon.content.FileLocation")
    assert trait_class == FileLocation

    # Nonexistent trait should return None
    no_trait = Representation.get_trait_class_by_trait_id(
        "ayon.test.NonExistent.v1")
    assert no_trait is None

    class NewTestTrait(TraitBase):
        """New test trait."""
        id = "ayon.test.NewTestTrait.v1"

    class AnotherCaseTrait(TraitBase):
        """Mixed case trait."""

        id = "Ayon.Test.AnotherCaseTrait.v1"

    class MixedCaseTrait(NewTestTrait, AnotherCaseTrait):
        """Mixed case trait."""
        id = "ayon.test.MixedCaseTrait.v1"

    trait_class = Representation.get_trait_class_by_trait_id(
        "ayon.test.MixedCaseTrait")
    assert trait_class == MixedCaseTrait


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

    with pytest.raises(
            IncompatibleTraitVersionError,
            match=(
                r"Requested trait version .* is higher than "
                r"the found trait version .*\.")):
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


def test_from_dict_nested_and_typed_values() -> None:
    """Nested traits, paths, patterns and enums are restored.

    Both `traits_as_dict()` output and its JSON serialized form (as stored
    on the server) must produce an equal representation.
    """
    import json
    import re

    from ayon_core.plugins.publish.integrate_traits import prepare_for_json

    representation = Representation(name="exr", traits=[
        FileLocations(file_paths=[
            FileLocation(
                file_path=Path(f"/path/to/render.{frame}.exr"),
                file_size=1024,
                file_hash="abc",
            )
            for frame in (1001, 1002)
        ]),
        FrameRanged(frame_start=1001, frame_end=1002),
        Sequence(
            frame_padding=4,
            gaps_policy=GapPolicy.missing,
            frame_regex=re.compile(
                r"render\.(?P<index>(?P<padding>0*)\d+)\.exr$"),
            frame_spec="1001-1002",
        ),
    ])
    trait_data = representation.traits_as_dict()
    json_data = json.loads(json.dumps(prepare_for_json(trait_data)))

    for data in (trait_data, json_data):
        result = Representation.from_dict(
            "exr",
            representation_id=representation.representation_id,
            trait_data=data,
        )
        assert result == representation
        file_paths = result.get_trait(FileLocations).file_paths
        assert all(isinstance(item, FileLocation) for item in file_paths)
        assert isinstance(file_paths[0].file_path, Path)
        sequence = result.get_trait(Sequence)
        assert sequence.gaps_policy is GapPolicy.missing
        assert isinstance(sequence.frame_regex, re.Pattern)
        result.validate()


def test_from_dict_bundle() -> None:
    """Bundle items are restored by their trait ids, also nested."""
    import json

    from ayon_core.plugins.publish.integrate_traits import prepare_for_json

    representation = Representation(name="bundle", traits=[
        Bundle(items=[
            [
                FileLocation(file_path=Path("/path/to/diffuse.png")),
                MimeType(mime_type="image/png"),
            ],
            [Bundle(items=[
                [FileLocation(file_path=Path("/path/to/bump.exr"))],
            ])],
        ]),
    ])
    trait_data = representation.traits_as_dict()
    assert trait_data[Bundle.id]["items"][0] == {
        FileLocation.id: {
            "file_path": Path("/path/to/diffuse.png"),
            "file_size": None,
            "file_hash": None,
        },
        MimeType.id: {"mime_type": "image/png"},
    }
    json_data = json.loads(json.dumps(prepare_for_json(trait_data)))

    for data in (trait_data, json_data):
        result = Representation.from_dict(
            "bundle",
            representation_id=representation.representation_id,
            trait_data=data,
        )
        assert result == representation


def test_representation_equality() -> None:
    """Test representation equality."""
    # rep_a and rep_b are equal
    rep_a = Representation(name="test", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
    ])
    rep_b = Representation(name="test", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
    ])

    # rep_c has different value for planar_configuration then rep_a and rep_b
    rep_c = Representation(name="test", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGBA"),
    ])

    rep_d = Representation(name="test", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
    ])
    rep_e = Representation(name="foo", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
    ])
    rep_f = Representation(name="foo", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Planar(planar_configuration="RGBA"),
    ])

    # let's assume ids are the same (because ids are randomly generated)
    rep_b.representation_id = rep_d.representation_id = rep_a.representation_id
    rep_c.representation_id = rep_e.representation_id = rep_a.representation_id
    rep_f.representation_id = rep_a.representation_id
    assert rep_a == rep_b

    # because of the trait value difference
    assert rep_a != rep_c
    # because of the type difference
    assert rep_a != "foo"
    # because of the trait count difference
    assert rep_a != rep_d
    # because of the name difference
    assert rep_d != rep_e
    # because of the trait difference
    assert rep_d != rep_f


def test_get_repre_by_name():
    """Test getting representation by name."""
    rep_a = Representation(name="test_a", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
    ])
    rep_b = Representation(name="test_b", traits=[
        FileLocation(file_path=Path("/path/to/file"), file_size=1024),
        Image(),
        PixelBased(
            display_window_width=1920,
            display_window_height=1080,
            pixel_aspect_ratio=1.0),
        Planar(planar_configuration="RGB"),
    ])

    representations = [rep_a, rep_b]
    _ = next(rep for rep in representations if rep.name == "test_a")
