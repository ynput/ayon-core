"""Tests for exporting trait definitions and their hashes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar, Optional

import pytest
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocations,
    Sequence,
    TraitBase,
)
from ayon_core.pipeline.traits.schema import (
    TRAITS_FORMAT,
    TraitSchemaError,
    collect_trait_classes,
    get_behavior_hash,
    get_core_hash,
    get_meta_hash,
    get_schema_hash,
    get_source_tokens,
    get_trait_definition,
    get_trait_hashes,
    parse_docstring,
    strip_schema_meta,
)
from ayon_core.pipeline.traits.utils import get_core_traits


class Kind(Enum):
    """Kind used by the test trait."""

    first = auto()
    second = auto()


@dataclass
class Sample(TraitBase):
    """Sample trait.

    Attributes:
        width (int): Width in pixels.
        label (Optional[str]): Label of
            the sample.
    """

    name: ClassVar[str] = "Sample"
    description: ClassVar[str] = "Sample Trait"
    id: ClassVar[str] = "test.schema.Sample.v1"
    persistent: ClassVar[bool] = True
    width: int
    label: Optional[str] = None

    def double_width(self) -> int:
        """Return double width."""
        return self.width * 2


@dataclass
class SampleMetaChanged(TraitBase):
    """Sample trait with different description.

    Attributes:
        width (int): Width of the sample in pixels.
        label (Optional[str]): Label.
    """

    name: ClassVar[str] = "Sample Renamed"
    description: ClassVar[str] = (
        "Sample trait with a much longer description"
    )
    id: ClassVar[str] = "test.schema.Sample.v1"
    persistent: ClassVar[bool] = True
    ui_hints: ClassVar[dict[str, Any]] = {"group": "Test"}
    width: int
    # comments do not change the behavior
    label: Optional[str] = None

    def double_width(self) -> int:
        return self.width * 2  # neither do trailing comments


@dataclass
class SampleBehaviorChanged(TraitBase):
    """Sample trait.

    Attributes:
        width (int): Width in pixels.
        label (Optional[str]): Label of
            the sample.
    """

    name: ClassVar[str] = "Sample"
    description: ClassVar[str] = "Sample Trait"
    id: ClassVar[str] = "test.schema.Sample.v1"
    persistent: ClassVar[bool] = True
    width: int
    label: Optional[str] = None

    def double_width(self) -> int:
        """Return double width."""
        return self.width + self.width + 1


@dataclass
class SampleSchemaChanged(TraitBase):
    """Sample trait.

    Attributes:
        width (int): Width in pixels.
        label (Optional[str]): Label of
            the sample.
    """

    name: ClassVar[str] = "Sample"
    description: ClassVar[str] = "Sample Trait"
    id: ClassVar[str] = "test.schema.Sample.v1"
    persistent: ClassVar[bool] = True
    width: float
    label: Optional[str] = None

    def double_width(self) -> int:
        """Return double width."""
        return self.width * 2


@dataclass
class Typed(TraitBase):
    """Trait using all supported field types.

    Args:
        path (Path): Path to a file.
        described (int): Description from docstring.

    """

    name: ClassVar[str] = "Typed"
    description: ClassVar[str] = "Typed Trait"
    id: ClassVar[str] = "test.schema.Typed.v1"
    persistent: ClassVar[bool] = False
    path: Path
    locations: FileLocations
    items: list[list[TraitBase]]
    pattern: Optional[re.Pattern] = None
    kind: Kind = Kind.second
    optional_kind: Optional[Kind] = None
    tags: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    pair: tuple[int, str] = (1, "a")
    anything: Any = None
    described: int = field(
        default=0, metadata={"description": "From metadata"})


@dataclass
class Unsupported(TraitBase):
    """Trait with a type which cannot be exported."""

    name: ClassVar[str] = "Unsupported"
    description: ClassVar[str] = "Unsupported Trait"
    id: ClassVar[str] = "test.schema.Unsupported.v1"
    value: complex


def test_parse_docstring() -> None:
    """Test summary and attribute descriptions are parsed."""
    summary, descriptions = parse_docstring(Sample.__doc__)
    assert summary == "Sample trait."
    assert descriptions == {
        "width": "Width in pixels.",
        "label": "Label of the sample.",
    }
    _, descriptions = parse_docstring(Typed.__doc__)
    assert descriptions["path"] == "Path to a file."
    assert parse_docstring(None) == ("", {})


def test_trait_definition() -> None:
    """Test definition of a simple trait."""
    definition = get_trait_definition(Sample)
    assert definition["id"] == "test.schema.Sample.v1"
    assert definition["versionlessId"] == "test.schema.Sample"
    assert definition["version"] == 1
    assert definition["name"] == "Sample"
    assert definition["description"] == "Sample Trait"
    assert definition["persistent"] is True
    assert "ui" not in definition

    schema = definition["schema"]
    assert schema["type"] == "object"
    assert schema["description"] == "Sample trait."
    assert list(schema["properties"]) == ["width", "label"]
    assert schema["properties"]["width"] == {
        "type": "integer",
        "description": "Width in pixels.",
    }
    assert schema["properties"]["label"]["type"] == ["string", "null"]
    assert schema["properties"]["label"]["default"] is None
    assert schema["required"] == ["width"]

    meta_definition = get_trait_definition(SampleMetaChanged)
    assert meta_definition["ui"] == {"group": "Test"}


def test_type_mapping() -> None:
    """Test conversion of field types to JSON Schema."""
    definition = get_trait_definition(Typed)
    assert definition["persistent"] is False
    schema = definition["schema"]
    props = schema["properties"]

    assert props["path"]["format"] == "path"
    assert props["pattern"] == {
        "type": ["string", "null"],
        "format": "regex",
        "default": None,
    }
    assert props["kind"]["enum"] == ["first", "second"]
    assert props["kind"]["default"] == "second"
    assert props["optional_kind"]["enum"] == ["first", "second", None]
    assert props["tags"] == {
        "type": "array",
        "items": {"type": "string"},
        "default": [],
    }
    assert props["data"] == {"type": "object", "default": {}}
    assert props["pair"]["prefixItems"] == [
        {"type": "integer"}, {"type": "string"}]
    assert props["pair"]["default"] == [1, "a"]
    assert props["anything"] == {"default": None}
    assert props["described"]["description"] == "From metadata"

    # Nested traits are referenced, including traits nested in them
    assert props["locations"] == {
        "$ref": f"#/$defs/{FileLocations.id}"}
    assert set(schema["$defs"]) == {
        FileLocations.id, "ayon.content.FileLocation.v2"}
    file_paths = schema["$defs"][FileLocations.id]["properties"]["file_paths"]
    assert file_paths["items"] == {
        "$ref": "#/$defs/ayon.content.FileLocation.v2"}

    # List of traits is stored as traits keyed by their id
    assert props["items"]["items"]["format"] == TRAITS_FORMAT
    assert schema["required"] == ["path", "locations", "items"]


def test_bundle_definition() -> None:
    """Test Bundle items are described as traits keyed by id."""
    schema = get_trait_definition(Bundle)["schema"]
    items = schema["properties"]["items"]
    assert items["type"] == "array"
    assert items["items"]["format"] == TRAITS_FORMAT


def test_sequence_enum_default() -> None:
    """Test enum default is stored by name, as it is serialized."""
    schema = get_trait_definition(Sequence)["schema"]
    assert schema["properties"]["gaps_policy"]["default"] == "forbidden"


def test_unsupported_type() -> None:
    """Test unsupported field type raises with trait and field name."""
    with pytest.raises(TraitSchemaError, match="Unsupported.v1.value"):
        get_trait_definition(Unsupported)


def test_strip_schema_meta() -> None:
    """Test only meta keywords are removed, not fields with such names."""
    schema = {
        "title": "Trait",
        "description": "Trait description",
        "properties": {
            "description": {"type": "string", "description": "Text"},
        },
        "items": {"title": "Item", "type": "string"},
        "anyOf": [{"description": "a", "type": "null"}],
    }
    assert strip_schema_meta(schema) == {
        "properties": {"description": {"type": "string"}},
        "items": {"type": "string"},
        "anyOf": [{"type": "null"}],
    }


def test_meta_change() -> None:
    """Test description and UI hint changes affect only the meta hash."""
    hashes = get_trait_hashes(Sample)
    changed = get_trait_hashes(SampleMetaChanged)
    assert changed["schema"] == hashes["schema"]
    assert changed["behavior"] == hashes["behavior"]
    assert changed["meta"] != hashes["meta"]


def test_behavior_change() -> None:
    """Test code change affects only the behavior hash."""
    hashes = get_trait_hashes(Sample)
    changed = get_trait_hashes(SampleBehaviorChanged)
    assert changed["schema"] == hashes["schema"]
    assert changed["behavior"] != hashes["behavior"]
    assert changed["meta"] == hashes["meta"]


def test_schema_change() -> None:
    """Test data model change affects the schema hash."""
    hashes = get_trait_hashes(Sample)
    changed = get_trait_hashes(SampleSchemaChanged)
    assert changed["schema"] != hashes["schema"]


def test_schema_hash_ignores_descriptions() -> None:
    """Test schema hash does not depend on titles and descriptions."""
    definition = get_trait_definition(Sample)
    schema_hash = get_schema_hash(definition)
    meta_hash = get_meta_hash(definition)
    definition["schema"]["properties"]["width"]["description"] = "Other"
    assert get_schema_hash(definition) == schema_hash
    assert get_meta_hash(definition) != meta_hash
    definition["persistent"] = False
    assert get_schema_hash(definition) != schema_hash


def test_source_tokens() -> None:
    """Test tokens are independent of formatting details."""
    tokens = get_source_tokens(Sample, {"name", "description"})
    assert "NAME:<name>" in tokens
    assert "NAME:Sample" not in tokens
    assert not any("Sample trait." in token for token in tokens)
    assert not any("Sample Trait" in token for token in tokens)
    assert "STRING:\"test.schema.Sample.v1\"" in tokens


def test_hash_stability() -> None:
    """Test hashes are stable across Python versions.

    The behavior hash is computed from tokens, which are the same in
    all supported Python versions. If the expected value changes, all
    released traits would be reported as changed.
    """
    assert get_behavior_hash(Sample) == (
        "sha256:"
        "0e5a79e2e486526a8cf0046cdf3202610aa5c558744279eb494970c507f75063"
    )
    assert get_schema_hash(get_trait_definition(Sample)) == (
        "sha256:"
        "dd39da24f350ab47672efdcfdc9178d011ec30d5015f1074c0438c41bd4469ae"
    )


def test_core_traits() -> None:
    """Test all core traits can be exported."""
    trait_classes = get_core_traits()
    assert trait_classes == collect_trait_classes(
        ["ayon_core.pipeline.traits"])
    trait_ids = [trait_class.id for trait_class in trait_classes]
    assert len(trait_ids) == len(set(trait_ids))
    assert "test.schema.Sample.v1" not in trait_ids
    assert FileLocations in trait_classes
    for trait_class in trait_classes:
        definition = get_trait_definition(trait_class)
        assert definition["version"] is not None, trait_class.id
        get_trait_hashes(trait_class, definition)
    assert get_core_hash().startswith("sha256:")
