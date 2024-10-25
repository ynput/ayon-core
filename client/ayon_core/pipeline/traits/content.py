"""Content traits for the pipeline."""
from __future__ import annotations

# TCH003 is there because Path in TYPECHECKING will fail in tests
from pathlib import Path  # noqa: TCH003
from typing import ClassVar, Optional

from pydantic import Field

from .trait import Representation, TraitBase


class MimeType(TraitBase):
    """MimeType trait model.

    This model represents a mime type trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        mime_type (str): Mime type.

    """

    name: ClassVar[str] = "MimeType"
    description: ClassVar[str] = "MimeType Trait Model"
    id: ClassVar[str] = "ayon.content.MimeType.v1"
    mime_type: str = Field(..., title="Mime Type")

class FileLocation(TraitBase):
    """FileLocation trait model.

    This model represents a file location trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        file_path (str): File path.
        file_size (int): File size in bytes.
        file_hash (str): File hash.

    """

    name: ClassVar[str] = "FileLocation"
    description: ClassVar[str] = "FileLocation Trait Model"
    id: ClassVar[str] = "ayon.content.FileLocation.v1"
    file_path: Path = Field(..., title="File Path")
    file_size: int = Field(..., title="File Size")
    file_hash: Optional[str] = Field(None, title="File Hash")

class RootlessLocation(TraitBase):
    """RootlessLocation trait model.

    This model represents a rootless location trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        rootless_path (str): Rootless path.

    """

    name: ClassVar[str] = "RootlessLocation"
    description: ClassVar[str] = "RootlessLocation Trait Model"
    id: ClassVar[str] = "ayon.content.RootlessLocation.v1"
    rootless_path: str = Field(..., title="File Path")


class Compressed(TraitBase):
    """Compressed trait model.

    This model represents a compressed trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        compression_type (str): Compression type.

    """

    name: ClassVar[str] = "Compressed"
    description: ClassVar[str] = "Compressed Trait"
    id: ClassVar[str] = "ayon.content.Compressed.v1"
    compression_type: str = Field(..., title="Compression Type")


class Bundle(TraitBase):
    """Bundle trait model.

    This model list of independent Representation traits
    that are bundled together. This is useful for representing
    a collection of representations that are part of a single
    entity.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        items (list[list[TraitBase]]): List of representations.

    """

    name: ClassVar[str] = "Bundle"
    description: ClassVar[str] = "Bundle Trait"
    id: ClassVar[str] = "ayon.content.Bundle.v1"
    items: list[list[TraitBase]] = Field(
        ..., title="Bundles of traits")

    def to_representation(self) -> Representation:
        """Convert to a representation."""
        return Representation(traits=self.items)


class Fragment(TraitBase):
    """Fragment trait model.

    This model represents a fragment trait. A fragment is a part of
    a larger entity that is represented by a representation.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        parent (str): Parent representation id.

    """

    name: ClassVar[str] = "Fragment"
    description: ClassVar[str] = "Fragment Trait"
    id: ClassVar[str] = "ayon.content.Fragment.v1"
    parent: str = Field(..., title="Parent Representation Id")
