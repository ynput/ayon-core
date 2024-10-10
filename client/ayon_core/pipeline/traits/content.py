"""Content traits for the pipeline."""
from __future__ import annotations

# TCH003 is there because Path in TYPECHECKING will fail in tests
from pathlib import Path  # noqa: TCH003
from typing import ClassVar, Optional

from pydantic import Field

from .trait import TraitBase


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
    file_hash: Optional[str] = Field(..., title="File Hash")

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
