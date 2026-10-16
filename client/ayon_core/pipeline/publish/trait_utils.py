"""Helpers for publish plugins working with trait representations.

Used by the trait-based extractors (review, transcode, burnin, thumbnail
and slate) to read files, tags and frame data of a `Representation` and to
create new representations from it, without converting them to legacy
representation dicts.

Functions work only with representations. Logic using publish instance
data (e.g. instance staging directory) is in `publish/lib.py`.
"""
from __future__ import annotations

import copy
import logging
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ayon_core.lib import StringTemplate
from ayon_core.pipeline.publish import PublishError
from ayon_core.pipeline.publish.trait_conversion import (
    sequence_traits_from_files,
)
from ayon_core.pipeline.publish.review_utils import DEFAULT_IMAGE_EXTS
from ayon_core.pipeline.traits import (
    ColorManaged,
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    Persistent,
    Representation,
    Sequence,
    StagingDirectory,
    Tagged,
    TraitBase,
    Variant,
)

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


def get_tags(representation: Representation) -> list[str]:
    """Get copy of tags of the representation.

    Args:
        representation (Representation): Representation.

    Returns:
        list[str]: Tags from `Tagged` trait.

    """
    if representation.contains_trait(Tagged):
        return list(representation.get_trait(Tagged).tags)
    return []


def set_tags(representation: Representation, tags: list[str]) -> None:
    """Set tags of the representation.

    Args:
        representation (Representation): Representation.
        tags (list[str]): Tags for `Tagged` trait.

    """
    if representation.contains_trait(Tagged):
        representation.get_trait(Tagged).tags = list(tags)
    else:
        representation.add_trait(Tagged(tags=list(tags)))


def get_variant(representation: Representation) -> str:
    """Get variant of the representation (`{output}` in templates).

    Args:
        representation (Representation): Representation.

    Returns:
        str: Variant or empty string.

    """
    if representation.contains_trait(Variant):
        return representation.get_trait(Variant).variant
    return ""


def set_variant(representation: Representation, variant: str) -> None:
    """Set or remove (empty value) variant of the representation.

    Args:
        representation (Representation): Representation.
        variant (str): Variant.

    """
    if representation.contains_trait(Variant):
        representation.remove_trait(Variant)
    if variant:
        representation.add_trait(Variant(variant=variant))


def get_file_paths(representation: Representation) -> list[Path]:
    """Get paths of files of the representation.

    Args:
        representation (Representation): Representation.

    Returns:
        list[Path]: File paths.

    Raises:
        PublishError: If representation does not have any files.

    """
    if representation.contains_trait(FileLocations):
        paths = [
            Path(path)
            for path in representation.get_trait(FileLocations).get_files()
        ]
    elif representation.contains_trait(FileLocation):
        paths = [Path(representation.get_trait(FileLocation).file_path)]
    else:
        paths = []

    if not paths:
        msg = f"Representation '{representation.name}' does not have files."
        raise PublishError(msg)
    return paths


def has_files(representation: Representation) -> bool:
    """Check if representation has any files.

    Args:
        representation (Representation): Representation.

    Returns:
        bool: Representation has files.

    """
    try:
        get_file_paths(representation)
    except PublishError:
        return False
    return True


def is_sequence(representation: Representation) -> bool:
    """Representation files are a list of files (`FileLocations`).

    Args:
        representation (Representation): Representation.

    Returns:
        bool: Representation has `FileLocations` trait.

    """
    return representation.contains_trait(FileLocations)


def get_ext(representation: Representation) -> str:
    """Get lowercase extension (without dot) of the representation files.

    Args:
        representation (Representation): Representation.

    Returns:
        str: Extension.

    """
    return get_file_paths(representation)[0].suffix.lstrip(".").lower()


def get_frame_rate(representation: Representation) -> Optional[float]:
    """Get frame rate of the representation from `FrameRanged` trait.

    Args:
        representation (Representation): Representation.

    Returns:
        Optional[float]: Frame rate or None if not set.

    """
    if not representation.contains_trait(FrameRanged):
        return None
    frame_rate = representation.get_trait(FrameRanged).frame_rate
    if frame_rate is None:
        return None
    return float(frame_rate)


def copy_representation(
        representation: Representation,
        name: Optional[str] = None,
        traits: Optional[list[type[TraitBase]]] = None) -> Representation:
    """Create new representation with copies of traits of the source.

    Args:
        representation (Representation): Source representation.
        name (Optional[str]): Name of the new representation. Name of
            the source is used if not passed.
        traits (Optional[list[type[TraitBase]]]): Copy only these traits.
            All traits are copied if not passed.

    Returns:
        Representation: New representation with new id.

    """
    if traits is None:
        source_traits = list(representation.get_traits().values())
    else:
        source_traits = [
            representation.get_trait(trait)
            for trait in traits
            if representation.contains_trait(trait)
        ]
    return Representation(
        name=name or representation.name,
        traits=[copy.deepcopy(trait) for trait in source_traits],
    )


def set_files(
        representation: Representation,
        paths: list[Path],
        *,
        sequence: bool,
        frame_rate: Optional[float] = None,
        update_frame_range: bool = False) -> None:
    """Point representation to new files.

    Replaces `FileLocation`/`FileLocations`, `Sequence`, `MimeType` and
    `Image` traits. For a sequence, the `Sequence` trait is created from
    the file names. `FrameRanged` is replaced by the frame range of the
    files when `update_frame_range` is set (or when it is missing).

    Args:
        representation (Representation): Representation to update.
        paths (list[Path]): Paths to the files.
        sequence (bool): Files are a sequence (list of files), single file
            otherwise.
        frame_rate (Optional[float]): Frame rate for new `FrameRanged`.
            Frame rate of the current `FrameRanged` is used if not passed.
        update_frame_range (bool): Replace `FrameRanged` with frame range
            of the files.

    """
    for trait in (FileLocation, FileLocations, Sequence, MimeType, Image):
        if representation.contains_trait(trait):
            representation.remove_trait(trait)

    if sequence:
        representation.add_trait(FileLocations(file_paths=[
            FileLocation(file_path=path) for path in paths
        ]))
        sequence_traits = sequence_traits_from_files(paths)
        if sequence_traits is not None:
            frame_ranged, sequence_trait = sequence_traits
            representation.add_trait(sequence_trait)
            has_frame_range = representation.contains_trait(FrameRanged)
            if update_frame_range or not has_frame_range:
                if frame_rate is None and has_frame_range:
                    frame_rate = representation.get_trait(
                        FrameRanged).frame_rate
                if has_frame_range:
                    representation.remove_trait(FrameRanged)
                frame_ranged.frame_rate = frame_rate
                representation.add_trait(frame_ranged)
    else:
        representation.add_trait(FileLocation(file_path=paths[0]))

    ext = paths[0].suffix.lstrip(".").lower()
    mime_type, _ = mimetypes.guess_type(f"file.{ext}")
    if mime_type:
        representation.add_trait(MimeType(mime_type=mime_type))
    if ext in DEFAULT_IMAGE_EXTS:
        representation.add_trait(Image())


def update_persistence(representation: Representation) -> None:
    """Mark representation `Persistent` unless it is tagged "delete".

    Representations tagged "delete" are intermediate, they are not
    integrated.

    Args:
        representation (Representation): Representation.

    """
    persistent = "delete" not in get_tags(representation)
    if persistent and not representation.contains_trait(Persistent):
        representation.add_trait(Persistent())
    elif not persistent and representation.contains_trait(Persistent):
        representation.remove_trait(Persistent)


def is_staging_persistent(representation: Representation) -> bool:
    """Files of the representation must be kept after publishing.

    Args:
        representation (Representation): Representation.

    Returns:
        bool: Staging directory of the representation is persistent.

    """
    if not representation.contains_trait(StagingDirectory):
        return False
    return representation.get_trait(StagingDirectory).is_persistent


def set_staging_directory(
        representation: Representation,
        path: Path,
        *,
        is_persistent: Optional[bool] = None) -> None:
    """Set staging directory of the representation files.

    Args:
        representation (Representation): Representation.
        path (Path): Staging directory.
        is_persistent (Optional[bool]): Files must be kept after
            publishing. Current persistence is kept if not passed.

    """
    if is_persistent is None:
        is_persistent = is_staging_persistent(representation)
    if representation.contains_trait(StagingDirectory):
        representation.remove_trait(StagingDirectory)
    representation.add_trait(StagingDirectory(
        path=Path(path), is_persistent=is_persistent
    ))


def get_ocio_config_path(
        color_managed: ColorManaged,
        anatomy: Anatomy,
        logger: Optional[logging.Logger] = None) -> Optional[str]:
    """Get path to OCIO config of color managed representation.

    Same as `get_representation_ocio_config_path` for `ColorManaged`
    trait. Config path is used if it exists, otherwise the config template
    is filled with environment variables and roots of the anatomy.

    Args:
        color_managed (ColorManaged): Color management trait.
        anatomy (Anatomy): Project anatomy.
        logger (Optional[logging.Logger]): Logger.

    Returns:
        Optional[str]: Path to existing OCIO config or None.

    """
    if logger is None:
        logger = logging.getLogger(__name__)

    config_path = color_managed.config_path
    config_template = color_managed.config_template
    if not config_path and not config_template:
        logger.warning("OCIO Config file is not set for representation.")
        return None

    if config_path:
        if os.path.isfile(config_path):
            return config_path
        logger.debug(
            f"OCIO Config file for representation not found at: {config_path}"
        )

    if not config_template:
        return None

    config_template = str(StringTemplate.format_template(
        config_template, os.environ.copy()
    ))
    config_path = anatomy.fill_root(config_template)
    if os.path.isfile(config_path):
        return config_path

    logger.warning(
        f"OCIO Config file for representation not found at: {config_path}"
    )
    return None
