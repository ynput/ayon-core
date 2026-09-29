"""Conversion helpers between trait `Representation` and legacy
representation dicts.

Used by the trait-based extractors to feed shared pipeline code that still
works on the dict shape (`ReviewRenderer`, `TranscodeRenderer`), and by host
integrations that build trait representations from data they already
resolve for legacy dicts (e.g. colorspace data).
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any, Optional

import clique

from ayon_core.pipeline.publish import PublishError
from ayon_core.pipeline.traits import (
    ColorManaged,
    CustomTags,
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    Persistent,
    PixelBased,
    Representation,
    Sequence,
    Tagged,
    TraitBase,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_IMAGE_EXTS,
)


def sequence_traits_from_files(
    paths: list[Path],
    fps: Optional[float] = None,
) -> Optional[tuple[FrameRanged, Sequence]]:
    """Create `FrameRanged` and `Sequence` traits describing files.

    `Sequence.frame_spec` lists the frames that exist (gaps included) and
    `Sequence.frame_regex` matches only files of this sequence (head and
    tail of the file names are part of the pattern).

    Args:
        paths (list[Path]): Paths of the sequence files.
        fps (Optional[float]): Frames per second.

    Returns:
        Optional[tuple[FrameRanged, Sequence]]: Traits or None if paths
            are not a single sequence.

    """
    collections, remainders = clique.assemble(
        [path.name for path in paths],
        patterns=[clique.PATTERNS["frames"]],
        minimum_items=1,
    )
    if remainders or len(collections) != 1:
        return None

    collection = collections[0]
    frames = sorted(collection.indexes)
    frame_ranged = FrameRanged(
        frame_start=frames[0],
        frame_end=frames[-1],
    )
    if fps:
        frame_ranged.frames_per_second = str(fps)

    # e.g. "1001-1010" or "1001-1005,1007-1010"
    frame_spec = collection.format("{ranges}").replace(" ", "")
    frame_regex = re.compile(
        re.escape(collection.head)
        + r"(?P<index>(?P<padding>0*)\d+)"
        + re.escape(collection.tail)
        + "$"
    )
    sequence = Sequence(
        # clique reports padding only for zero-padded frame numbers
        frame_padding=collection.padding or len(str(frames[-1])),
        frame_regex=frame_regex,
        frame_spec=frame_spec,
    )
    return frame_ranged, sequence


def color_managed_from_colorspace_data(
    colorspace_data: Optional[dict[str, Any]],
) -> Optional[ColorManaged]:
    """Create `ColorManaged` trait from legacy "colorspaceData" dict.

    Args:
        colorspace_data (Optional[dict[str, Any]]): Data in the shape set by
            `set_colorspace_data_to_representation` - "colorspace", "config"
            with "path"/"template" and optional "display"/"view".

    Returns:
        Optional[ColorManaged]: Trait or None if no colorspace is set.

    """
    if not colorspace_data or not colorspace_data.get("colorspace"):
        return None
    config = colorspace_data.get("config") or {}
    return ColorManaged(
        color_space=colorspace_data["colorspace"],
        config_path=config.get("path"),
        config_template=config.get("template"),
        display=colorspace_data.get("display"),
        view=colorspace_data.get("view"),
    )


def representation_to_legacy_dict(representation: Representation) -> dict:
    """Convert a trait Representation into the internal repre-dict shape
    the shared renderers expect (name/ext/files/stagingDir/tags/
    custom_tags, plus colorspaceData when ColorManaged is present).

    This dict is an internal DTO only - it is never appended to
    `instance.data["representations"]`, just fed into shared pipeline code
    that still speaks the legacy dict shape.

    Raises:
        PublishError: If the representation has neither FileLocation nor
            FileLocations trait, or FileLocations is empty.

    """
    tags: list[str] = []
    if representation.contains_trait(Tagged):
        tags = list(representation.get_trait(Tagged).tags)

    if representation.contains_trait(FileLocations):
        file_locs = representation.get_trait(FileLocations)
        if not file_locs.file_paths:
            raise PublishError(
                f"Representation '{representation.name}' has an empty "
                "FileLocations trait."
            )
        staging_dir = str(file_locs.get_common_root())
        files = [Path(f.file_path).name for f in file_locs.file_paths]
        ext = Path(file_locs.file_paths[0].file_path).suffix.lstrip(".")
    elif representation.contains_trait(FileLocation):
        file_loc = representation.get_trait(FileLocation)
        file_path = Path(file_loc.file_path)
        staging_dir = str(file_path.parent)
        files = file_path.name
        ext = file_path.suffix.lstrip(".")
    else:
        raise PublishError(
            f"Representation '{representation.name}' has neither "
            "FileLocation nor FileLocations trait."
        )

    result: dict[str, Any] = {
        "name": representation.name,
        "ext": ext.lower(),
        "files": files,
        "stagingDir": staging_dir,
        "tags": tags,
    }
    if representation.contains_trait(CustomTags):
        result["custom_tags"] = list(
            representation.get_trait(CustomTags).tags
        )

    if representation.contains_trait(ColorManaged):
        cm = representation.get_trait(ColorManaged)
        colorspace_data = {
            "colorspace": cm.color_space,
            "config": {
                "path": cm.config_path,
                "template": cm.config_template,
            },
        }
        # Optional keys in legacy "colorspaceData" - only set when present.
        if cm.display:
            colorspace_data["display"] = cm.display
        if cm.view:
            colorspace_data["view"] = cm.view
        result["colorspaceData"] = colorspace_data

    return result


def legacy_dict_to_representation(
    new_repre: dict[str, Any],
    source: Optional[Representation] = None,
) -> Representation:
    """Convert one renderer-output dict back into a Representation.

    If `new_repre` carries `colorspaceData` (set or updated by the shared
    renderer, e.g. `TranscodeRenderer` changing the target colorspace),
    that becomes the result's `ColorManaged` trait. Otherwise `ColorManaged`
    is carried over unchanged from `source` (the common case - most
    renderers, e.g. `ReviewRenderer`, never touch color).

    `source` can be omitted when the dict was not derived from another
    trait representation (e.g. a host converting its own legacy dicts).

    Marks the result `Persistent` unless it carries the legacy "delete"
    tag (mirrors `ExtractReview.process`'s cleanup pass, which removes
    "delete"-tagged representations rather than integrating them).
    """
    traits: list[TraitBase] = []

    files = new_repre["files"]
    staging_dir = Path(new_repre["stagingDir"])
    if isinstance(files, (list, tuple)):
        file_paths = [
            FileLocation(file_path=staging_dir / filename)
            for filename in files
        ]
        traits.append(FileLocations(file_paths=file_paths))
        sequence_traits = sequence_traits_from_files(
            [staging_dir / filename for filename in files],
            fps=new_repre.get("fps"),
        )
        if sequence_traits is not None:
            traits.extend(sequence_traits)
    else:
        traits.append(FileLocation(file_path=staging_dir / files))

    ext = new_repre["ext"]
    mime_type, _ = mimetypes.guess_type(f"file.{ext}")
    if mime_type:
        traits.append(MimeType(mime_type=mime_type))
    if ext in DEFAULT_IMAGE_EXTS:
        traits.append(Image())

    width = new_repre.get("resolutionWidth")
    height = new_repre.get("resolutionHeight")
    if width and height:
        traits.append(PixelBased(
            display_window_width=width,
            display_window_height=height,
            pixel_aspect_ratio=1.0,
        ))

    tags = list(new_repre.get("tags") or [])
    traits.append(Tagged(tags=tags))
    custom_tags = new_repre.get("custom_tags")
    if custom_tags:
        traits.append(CustomTags(tags=list(custom_tags)))

    color_managed = color_managed_from_colorspace_data(
        new_repre.get("colorspaceData")
    )
    if color_managed is not None:
        traits.append(color_managed)
    elif source is not None and source.contains_trait(ColorManaged):
        traits.append(source.get_trait(ColorManaged))

    if "delete" not in tags:
        traits.append(Persistent())

    return Representation(name=new_repre["name"], traits=traits)
