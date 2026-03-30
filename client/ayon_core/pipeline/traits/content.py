"""Content traits for the pipeline."""
from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass

# TCH003 is there because Path in TYPECHECKING will fail in tests
from pathlib import Path  # noqa: TCH003
from typing import ClassVar, Generator, Optional

from clique import assemble

from .representation import Representation
from .temporal import FrameRanged, Handles, Sequence
from .trait import (
    MissingTraitError,
    TraitBase,
    TraitValidationError,
)
from .two_dimensional import UDIM


@dataclass
class MimeType(TraitBase):
    """MimeType trait model.

    This model represents a mime type trait. For example, image/jpeg.
    It is used to describe the type of content in a representation regardless
    of the file extension.

    For more information, see RFC 2046 and RFC 4288 (and related RFCs).

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        mime_type (str): Mime type like image/jpeg.
    """

    name: ClassVar[str] = "MimeType"
    description: ClassVar[str] = "MimeType Trait Model"
    id: ClassVar[str] = "ayon.content.MimeType.v1"
    persistent: ClassVar[bool] = True
    mime_type: str


@dataclass
class LocatableContent(TraitBase):
    """LocatableContent trait model.

    This model represents a locatable content trait. Locatable content
    is content that has a location. It doesn't have to be a file - it could
    be a URL or some other location.

    Sync with OpenAssetIO MediaCreation Traits.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        location (str): Location.
        is_templated (Optional[bool]): Is the location templated?
            Default is None.
    """

    name: ClassVar[str] = "LocatableContent"
    description: ClassVar[str] = "LocatableContent Trait Model"
    id: ClassVar[str] = "ayon.content.LocatableContent.v1"
    persistent: ClassVar[bool] = True
    location: str
    is_templated: Optional[bool] = None


@dataclass
class FileLocation(TraitBase):
    """FileLocation trait model.

    This model represents a file path. It is a specialization of the
    LocatableContent trait. It is adding optional file size and file hash
    for easy access to file information.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        file_path (str): File path.
        file_size (Optional[int]): File size in bytes.
        file_hash (Optional[str]): File hash.
    """

    name: ClassVar[str] = "FileLocation"
    description: ClassVar[str] = "FileLocation Trait Model"
    id: ClassVar[str] = "ayon.content.FileLocation.v1"
    persistent: ClassVar[bool] = True
    file_path: Path
    file_size: Optional[int] = None
    file_hash: Optional[str] = None


@dataclass
class FileLocations(TraitBase):
    """FileLocations trait model.

    This model defines list of FileLocation traits. It can be
    used for file sequences or more complex hierarchies.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        file_paths (list of FileLocation): File locations.

    """

    name: ClassVar[str] = "FileLocations"
    description: ClassVar[str] = "FileLocations Trait Model"
    id: ClassVar[str] = "ayon.content.FileLocations.v1"
    persistent: ClassVar[bool] = True
    file_paths: list[FileLocation]

    def get_files(self) -> Generator[Path, None, None]:
        """Get all file paths from the trait.

        This method will return all file paths from the trait.

        Yields:
            Path: List of file paths.

        """
        for file_location in self.file_paths:
            yield file_location.file_path

    def get_common_root(self) -> Path:
        """Get a meaningful common root directory for all file paths.

        Returns:
            Path: Common root directory.

        Raises:
            ValueError: If file locations do not share a meaningful root.

        """
        file_paths = [
            file_path if isinstance(file_path, Path) else Path(file_path)
            for file_path in self.get_files()
        ]
        if not file_paths:
            raise ValueError("No file locations defined.")

        try:
            common_root = Path(
                os.path.commonpath(
                    [str(file_path.parent) for file_path in file_paths]
                )
            )
        except ValueError as exc:
            raise ValueError(
                "File locations must share a common root directory."
            ) from exc

        if str(common_root) in {"", "."}:
            raise ValueError(
                "File locations must share a meaningful common root directory."
            )

        if common_root.anchor and common_root == Path(common_root.anchor):
            raise ValueError(
                "File locations must share a common root deeper than the "
                "filesystem root."
            )

        return common_root

    def get_file_location_for_frame(
            self,
            frame: int,
            sequence_trait: Optional[Sequence] = None,
        ) -> Optional[FileLocation]:
        """Get a file location for a frame.

        This method will return the file location for a given frame. If the
        frame is not found in the file paths, it will return None.

        Args:
            frame (int): Frame to get the file location for.
            sequence_trait (Sequence): Sequence trait to get the
                frame range specs from.

        Returns:
            Optional[FileLocation]: File location for the frame.

        """
        frame_regex = re.compile(r"\.(?P<index>(?P<padding>0*)\d+)\.\D+\d?$")
        if sequence_trait and sequence_trait.frame_regex:
            frame_regex = sequence_trait.get_frame_pattern()

        for location in self.file_paths:
            result = re.search(frame_regex, location.file_path.name)
            if result:
                frame_index = int(result.group("index"))
                if frame_index == frame:
                    return location
        return None

    def validate_trait(self, representation: Representation) -> None:
        """Validate the trait.

        This method validates the trait against others in the representation.
        In particular, it checks that the sequence trait is present, and if
        so, it will compare the frame range to the file paths.

        Args:
            representation (Representation): Representation to validate.

        Raises:
            TraitValidationError: If the trait is invalid within the
                representation.

        """
        super().validate_trait(representation)
        if len(self.file_paths) == 0:
            # If there are no file paths, we can't validate
            msg = "No file locations defined (empty list)"
            raise TraitValidationError(self.name, msg)
        if representation.contains_trait(FrameRanged):
            self._validate_frame_range(representation)
        if not representation.contains_trait(Sequence) \
                and not representation.contains_trait(UDIM):
            try:
                self.get_common_root()
            except ValueError as exc:
                msg = (
                    "Multiple file locations defined, but no Sequence or "
                    "UDIM trait defined. Files must share a meaningful "
                    "common root so their relative hierarchy can be "
                    "preserved."
                )
                raise TraitValidationError(self.name, msg) from exc

    def _validate_frame_range(self, representation: Representation) -> None:
        """Validate the frame range against the file paths.

        If the representation contains a FrameRanged trait, this method will
        validate the frame range against the file paths. If the frame range
        does not match the file paths, the trait is invalid. It takes into
        account the Handles and Sequence traits.

        Args:
            representation (Representation): Representation to validate.

        Raises:
            TraitValidationError: If the trait is invalid within the
                representation.

        """
        tmp_frame_ranged: FrameRanged = self.get_sequence_from_files(
                    [f.file_path for f in self.file_paths])

        frames_from_spec: list[int] = []
        with contextlib.suppress(MissingTraitError):
            sequence: Sequence = representation.get_trait(Sequence)
            frame_regex = sequence.get_frame_pattern()
            if sequence.frame_spec:
                frames_from_spec = sequence.get_frame_list(
                    self, frame_regex)

        frame_start_with_handles, frame_end_with_handles = \
            self._get_frame_info_with_handles(representation, frames_from_spec)

        if frame_start_with_handles \
                and tmp_frame_ranged.frame_start != frame_start_with_handles:
            # If the detected frame range does not match the combined
            # FrameRanged and Handles trait, the
            # trait is invalid.
            msg = (
                f"Frame range defined by {self.name} "
                f"({tmp_frame_ranged.frame_start}-"
                f"{tmp_frame_ranged.frame_end}) "
                "in files does not match "
                "frame range "
                f"({frame_start_with_handles}-"
                f"{frame_end_with_handles}) defined in FrameRanged trait."
            )

            raise TraitValidationError(self.name, msg)

        if frames_from_spec:
            if len(frames_from_spec) != len(self.file_paths):
                # If the number of file paths does not match the frame range,
                # the trait is invalid
                msg = (
                    f"Number of file locations ({len(self.file_paths)}) "
                    "does not match frame range defined by frame spec "
                    "on Sequence trait: "
                    f"({len(frames_from_spec)})"
                )
                raise TraitValidationError(self.name, msg)
            # if there is a frame spec on the Sequence trait,
            # we should not validate the frame range from the files.
            # the rest is validated by Sequence validators.
            return

        length_with_handles: int = (
            frame_end_with_handles - frame_start_with_handles + 1
        )

        if len(self.file_paths) != length_with_handles:
            # If the number of file paths does not match the frame range,
            # the trait is invalid
            msg = (
                f"Number of file locations ({len(self.file_paths)}) "
                "does not match frame range "
                f"({length_with_handles})"
            )
            raise TraitValidationError(self.name, msg)

        frame_ranged: FrameRanged = representation.get_trait(FrameRanged)

        if frame_start_with_handles != tmp_frame_ranged.frame_start or \
                frame_end_with_handles != tmp_frame_ranged.frame_end:
            # If the frame range does not match the FrameRanged trait, the
            # trait is invalid. Note that we don't check the frame rate
            # because it is not stored in the file paths and is not
            # determined by `get_sequence_from_files`.
            msg = (
                "Frame range "
                f"({frame_ranged.frame_start}-{frame_ranged.frame_end}) "
                "in sequence trait does not match "
                "frame range "
                f"({tmp_frame_ranged.frame_start}-"
                f"{tmp_frame_ranged.frame_end}) "
            )
            raise TraitValidationError(self.name, msg)

    @staticmethod
    def _get_frame_info_with_handles(
            representation: Representation,
            frames_from_spec: list[int]) -> tuple[int, int]:
        """Get the frame range with handles from the representation.

        This will return frame start and frame end with handles calculated
        in if there actually is the Handles trait in the representation.

        Args:
            representation (Representation): Representation to get the frame
                range from.
            frames_from_spec (list[int]): List of frames from the frame spec.
                This list is modified in place to take into
                account the handles.

        Mutates:
            frames_from_spec: List of frames from the frame spec.

        Returns:
            tuple[int, int]: Start and end frame with handles.

        """
        frame_start = frame_end = 0
        frame_start_handle = frame_end_handle = 0
        # If there is no sequence trait, we can't validate it
        if frames_from_spec and representation.contains_trait(FrameRanged):
            # if there is no FrameRanged trait (but really there should be)
            # we can use the frame range from the frame spec
            frame_start = min(frames_from_spec)
            frame_end = max(frames_from_spec)

        # Handle the frame range
        with contextlib.suppress(MissingTraitError):
            frame_start = representation.get_trait(FrameRanged).frame_start
            frame_end = representation.get_trait(FrameRanged).frame_end

        # Handle the handles :P
        with contextlib.suppress(MissingTraitError):
            handles: Handles = representation.get_trait(Handles)
            if not handles.inclusive:
                # if handless are exclusive, we need to adjust the frame range
                frame_start_handle = handles.frame_start_handle or 0
                frame_end_handle = handles.frame_end_handle or 0
                if frames_from_spec:
                    frames_from_spec.extend(
                        range(frame_start - frame_start_handle, frame_start)
                    )
                    frames_from_spec.extend(
                        range(frame_end + 1, frame_end_handle + frame_end + 1)
                    )

        frame_start_with_handles = frame_start - frame_start_handle
        frame_end_with_handles = frame_end + frame_end_handle

        return frame_start_with_handles, frame_end_with_handles

    @staticmethod
    def get_sequence_from_files(paths: list[Path]) -> FrameRanged:
        """Get the original frame range from files.

        Note that this cannot guess frame rate, so it's set to 25.
        This will also fail on paths that cannot be assembled into
        one collection without any reminders.

        Args:
            paths (list[Path]): List of file paths.

        Returns:
            FrameRanged: FrameRanged trait.

        Raises:
            ValueError: If paths cannot be assembled into one collection

        """
        cols, rems = assemble([path.as_posix() for path in paths])
        if rems:
            msg = "Cannot assemble paths into one collection"
            raise ValueError(msg)
        if len(cols) != 1:
            msg = "More than one collection found"
            raise ValueError(msg)
        col = cols[0]

        sorted_frames = sorted(col.indexes)
        # First frame used for end value
        first_frame = sorted_frames[0]
        # Get last frame for padding
        last_frame = sorted_frames[-1]
        # Use padding from a collection of the last frame lengths as string
        # padding = max(col.padding, len(str(last_frame)))

        return FrameRanged(
            frame_start=first_frame, frame_end=last_frame,
            frames_per_second="25.0"
        )


@dataclass
class RootlessLocation(TraitBase):
    """RootlessLocation trait model.

    RootlessLocation trait is a trait that represents a file path that is
    without a specific root. To get the absolute path, the root needs to be
    resolved by AYON. Rootless path can be used on multiple platforms.

    Example::

        RootlessLocation(
            rootless_path="{root[work]}/project/asset/asset.jpg"
        )

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        rootless_path (str): Rootless path.
    """

    name: ClassVar[str] = "RootlessLocation"
    description: ClassVar[str] = "RootlessLocation Trait Model"
    id: ClassVar[str] = "ayon.content.RootlessLocation.v1"
    persistent: ClassVar[bool] = True
    rootless_path: str


@dataclass
class Compressed(TraitBase):
    """Compressed trait model.

    This trait can hold information about compressed content. What type
    of compression is used.

    Example::

        Compressed("gzip")

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        compression_type (str): Compression type.
    """

    name: ClassVar[str] = "Compressed"
    description: ClassVar[str] = "Compressed Trait"
    id: ClassVar[str] = "ayon.content.Compressed.v1"
    persistent: ClassVar[bool] = True
    compression_type: str


@dataclass
class Bundle(TraitBase):
    """Bundle trait model.

    This model list of independent Representation traits
    that are bundled together. This is useful for representing
    a collection of sub-entities that are part of a single
    entity. You can easily reconstruct representations from
    the bundle.

    Example::

            Bundle(
                items=[
                    [
                        MimeType(mime_type="image/jpeg"),
                        FileLocation(file_path="/path/to/file.jpg")
                    ],
                    [

                        MimeType(mime_type="image/png"),
                        FileLocation(file_path="/path/to/file.png")
                    ]
                ]
            )

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with version
        items (list[list[TraitBase]]): List of representations.
    """

    name: ClassVar[str] = "Bundle"
    description: ClassVar[str] = "Bundle Trait"
    id: ClassVar[str] = "ayon.content.Bundle.v1"
    persistent: ClassVar[bool] = True
    items: list[list[TraitBase]]

    def to_representations(self) -> Generator[Representation]:
        """Convert a bundle to representations.

        Yields:
            Representation: Representation of the bundle.

        """
        for idx, item in enumerate(self.items):
            yield Representation(name=f"{self.name} {idx}", traits=item)


@dataclass
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
    persistent: ClassVar[bool] = True
    parent: str


@dataclass
class OriginalFilename(TraitBase):
    """OriginalFilename trait model.

    This trait indicates that the representation file name(s) are kept -
    ie they are not renamed using templates

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "OriginalFilename"
    description: ClassVar[str] = "OriginalFilename Trait"
    id: ClassVar[str] = "ayon.content.OriginalFilename.v1"
    persistent: ClassVar[bool] = True
