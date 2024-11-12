"""Content traits for the pipeline."""
from __future__ import annotations

# TCH003 is there because Path in TYPECHECKING will fail in tests
from pathlib import Path  # noqa: TCH003
from typing import ClassVar, Optional

from pydantic import Field

from .representation import Representation
from .time import FrameRanged
from .trait import (
    MissingTraitError,
    TraitBase,
    TraitValidationError,
)
from .utils import get_sequence_from_files


class MimeType(TraitBase):
    """MimeType trait model.

    This model represents a mime type trait. For example, image/jpeg.
    It is used to describe the type of content in a representation regardless
    of the file extension.

    For more information, see RFC 2046 and RFC 4288 (and related RFCs).

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        mime_type (str): Mime type like image/jpeg.

    """

    name: ClassVar[str] = "MimeType"
    description: ClassVar[str] = "MimeType Trait Model"
    id: ClassVar[str] = "ayon.content.MimeType.v1"
    mime_type: str = Field(..., title="Mime Type")

class LocatableContent(TraitBase):
    """LocatableContent trait model.

    This model represents a locatable content trait. Locatable content
    is content that has a location. It doesn't have to be a file - it could
    be a URL or some other location.

    Sync with OpenAssetIO MediaCreation Traits.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        location (str): Location.

    """

    name: ClassVar[str] = "LocatableContent"
    description: ClassVar[str] = "LocatableContent Trait Model"
    id: ClassVar[str] = "ayon.content.LocatableContent.v1"
    location: str = Field(..., title="Location")
    is_templated: Optional[bool] = Field(None, title="Is Templated")

class FileLocation(TraitBase):
    """FileLocation trait model.

    This model represents a file path. It is a specialization of the
    LocatableContent trait. It is adding optional file size and file hash
    for easy access to file information.

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
    file_size: Optional[int] = Field(None, title="File Size")
    file_hash: Optional[str] = Field(None, title="File Hash")

class FileLocations(TraitBase):
    """FileLocation trait model.

    This model represents a file path. It is a specialization of the
    LocatableContent trait. It is adding optional file size and file hash
    for easy access to file information.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        file_paths (list of FileLocation): File locations.

    """

    name: ClassVar[str] = "FileLocations"
    description: ClassVar[str] = "FileLocations Trait Model"
    id: ClassVar[str] = "ayon.content.FileLocations.v1"
    file_paths: list[FileLocation] = Field(..., title="File Path")

    def validate(self, representation: Representation) -> bool:
        """Validate the trait.

        This method validates the trait against others in the representation.
        In particular, it checks that the sequence trait is present and if
        so, it will compare the frame range to the file paths.

        Args:
            representation (Representation): Representation to validate.

        Returns:
            bool: True if the trait is valid, False otherwise

        """
        if len(self.file_paths) == 0:
                # If there are no file paths, we can't validate
                msg = "No file locations defined (empty list)"
                raise TraitValidationError(self.name, msg)

        tmp_frame_ranged: FrameRanged = get_sequence_from_files(
                    [f.file_path for f in self.file_paths])

        if len(self.file_paths) - 1 != \
                    tmp_frame_ranged.frame_end - tmp_frame_ranged.frame_start:
                # If the number of file paths does not match the frame range,
                # the trait is invalid
                msg = (
                    f"Number of file locations ({len(self.file_paths) - 1}) "
                    "does not match frame range "
                    f"({tmp_frame_ranged.frame_end - tmp_frame_ranged.frame_start})"
                )
                raise TraitValidationError(self.name, msg)

        try:
            sequence: FrameRanged = representation.get_trait(FrameRanged)

            if sequence.frame_start != tmp_frame_ranged.frame_start or \
                    sequence.frame_end != tmp_frame_ranged.frame_end:
                # If the frame range does not match the sequence trait, the
                # trait is invalid. Note that we don't check the frame rate
                # because it is not stored in the file paths and is not
                # determined by `get_sequence_from_files`.
                msg = (
                    "Frame range "
                    f"({sequence.frame_start}-{sequence.frame_end}) "
                    "in sequence trait does not match "
                    "frame range "
                    f"({tmp_frame_ranged.frame_start}-{tmp_frame_ranged.frame_end}) "
                    "defined in files."
                )
                raise TraitValidationError(self.name, msg)

        except MissingTraitError:
            # If there is no sequence trait, we can't validate it
            pass


class RootlessLocation(TraitBase):
    """RootlessLocation trait model.

    RootlessLocation trait is a trait that represents a file path that is
    without specific root. To obtain absolute path, the root needs to be
    resolved by AYON. Rootless path can be used on multiple platforms.

    Example::

        RootlessLocation(
            rootless_path="{root[work]}/project/asset/asset.jpg"
        )

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

    This trait can hold information about compressed content. What type
    of compression is used.

    Example::

        Compressed("gzip")

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

    Example::

            Bundle(
                items=[
                    [
                        Representation(
                            traits=[
                                MimeType(mime_type="image/jpeg"),
                                FileLocation(file_path="/path/to/file.jpg")
                            ]
                        )
                    ],
                    [
                        Representation(
                            traits=[
                                MimeType(mime_type="image/png"),
                                FileLocation(file_path="/path/to/file.png")
                            ]
                        )
                    ]
                ]
            )

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
    a larger entity that is represented by another representation.

    Example::

        main_representation = Representation(name="parent",
            traits=[],
        )
        fragment_representation = Representation(
            name="fragment",
            traits=[
                Fragment(parent=main_representation.id),
            ]
        )

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
