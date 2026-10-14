"""Conversion helpers between trait `Representation` and legacy
representation dicts.

Used by host integrations that build trait representations from data they
already resolve for legacy dicts (e.g. colorspace data or representations
created by host exporters). Trait-based extractors work with traits
directly, see `trait_utils.py`.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

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
    ReviewOutput,
    Sequence,
    Slate,
    StagingDirectory,
    Tagged,
    TraitBase,
    Variant,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_IMAGE_EXTS,
)

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


# legacy representation keys set by review extractor, used by burnins
#   and slate
REVIEW_OUTPUT_KEYS = (
    "ffmpeg_cmd",
    "source_resolution_width",
    "source_resolution_height",
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
        frame_ranged.frame_rate = fps

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
    """Convert a trait Representation into the legacy repre-dict shape
    (name/ext/files/stagingDir/tags/custom_tags, plus colorspaceData,
    resolution, fps, slate "data" and review output keys when the matching
    traits are present).

    Inverse of `legacy_dict_to_representation`, for code that still
    speaks the legacy dict shape.

    Args:
        representation (Representation): The representation to convert.

    Returns:
        dict: The legacy dictionary representation of the representation.

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
        file_paths = [Path(f.file_path) for f in file_locs.file_paths]
        staging_dir = file_locs.get_common_root()
    elif representation.contains_trait(FileLocation):
        file_paths = [
            Path(representation.get_trait(FileLocation).file_path)]
        staging_dir = file_paths[0].parent
    else:
        raise PublishError(
            f"Representation '{representation.name}' has neither "
            "FileLocation nor FileLocations trait."
        )

    staging_persistent = False
    if representation.contains_trait(StagingDirectory):
        staging_directory = representation.get_trait(StagingDirectory)
        staging_dir = Path(staging_directory.path)
        staging_persistent = staging_directory.is_persistent

    # file names are relative to the staging directory, they can contain
    #   subdirectories
    try:
        filenames = [
            path.relative_to(staging_dir).as_posix() for path in file_paths
        ]
    except ValueError as exc:
        raise PublishError(
            f"Files of representation '{representation.name}' are not"
            f" in its staging directory '{staging_dir}'."
        ) from exc

    files: Any = filenames
    if not representation.contains_trait(FileLocations):
        files = filenames[0]

    result: dict[str, Any] = {
        "name": representation.name,
        "ext": file_paths[0].suffix.lstrip(".").lower(),
        "files": files,
        "stagingDir": str(staging_dir),
        "tags": tags,
    }
    if staging_persistent:
        result["stagingDir_persistent"] = True
    if representation.contains_trait(CustomTags):
        result["custom_tags"] = list(
            representation.get_trait(CustomTags).tags
        )
    # legacy "outputName" fills `{output}` in publish templates,
    # `Variant` is used for it on trait representations
    if representation.contains_trait(Variant):
        result["outputName"] = representation.get_trait(Variant).variant

    if representation.contains_trait(PixelBased):
        pixel_based = representation.get_trait(PixelBased)
        result["resolutionWidth"] = pixel_based.display_window_width
        result["resolutionHeight"] = pixel_based.display_window_height

    if representation.contains_trait(FrameRanged):
        frame_rate = representation.get_trait(FrameRanged).frame_rate
        if frame_rate is not None:
            result["fps"] = float(frame_rate)

    if representation.contains_trait(Slate):
        result["data"] = {
            "slateFrames": representation.get_trait(Slate).frames
        }

    if representation.contains_trait(ReviewOutput):
        review_output = representation.get_trait(ReviewOutput)
        result["burnins"] = list(review_output.burnins)
        for key in REVIEW_OUTPUT_KEYS:
            value = getattr(review_output, key)
            if value is not None:
                result[key] = value
        if review_output.output_def is not None:
            result["outputDef"] = review_output.output_def

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
    *,
    default_staging_dir: Optional[str] = None,
    anatomy: Optional[Anatomy] = None,
) -> Representation:
    """Convert one renderer-output dict back into a Representation.

    If `new_repre` carries `colorspaceData` (set or updated by the shared
    renderer, e.g. `TranscodeRenderer` changing the target colorspace),
    that becomes the result's `ColorManaged` trait. Otherwise `ColorManaged`
    is carried over unchanged from `source`.

    `source` can be omitted when the dict was not derived from another
    trait representation (e.g. a host converting its own legacy dicts).

    Slate frames (`data["slateFrames"]`) become the `Slate` trait and
    the keys set by the review extractor for burnins and slate
    (`burnins`, `ffmpeg_cmd`, `outputDef`, ...) become the non-persistent
    `ReviewOutput` trait.

    Marks the result `Persistent` unless it carries the legacy "delete"
    tag (mirrors `ExtractReview.process`'s cleanup pass, which removes
    "delete"-tagged representations rather than integrating them).

    "stagingDir" (with "stagingDir_persistent") becomes the
    `StagingDirectory` trait. Representation dicts can rely on the staging
    directory of their instance - pass it as `default_staging_dir` (see
    `convert_legacy_representations` for conversion with instance data).
    Root templates in the staging directory (e.g. "{root[work]}") are
    filled when `anatomy` is passed.

    Args:
        new_repre (dict[str, Any]): The legacy representation dictionary.
        source (Optional[Representation]): The source representation
            to inherit traits from.
        default_staging_dir (Optional[str]): Staging directory used if
            the dict does not have "stagingDir".
        anatomy (Optional[Anatomy]): Project anatomy to fill roots in
            the staging directory.

    Raises:
        PublishError: If the staging directory is not set.

    Returns:
        Representation: The converted representation instance.

    """
    traits: list[TraitBase] = []

    files = new_repre["files"]
    staging_dir_value = new_repre.get("stagingDir") or default_staging_dir
    if not staging_dir_value:
        raise PublishError(
            "No staging directory set for representation"
            f" '{new_repre['name']}'."
        )
    if anatomy is not None:
        staging_dir_value = anatomy.fill_root(staging_dir_value)
    staging_dir = Path(staging_dir_value)
    traits.append(StagingDirectory(
        path=staging_dir,
        is_persistent=bool(new_repre.get("stagingDir_persistent")),
    ))
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
    output_name = new_repre.get("outputName")
    if output_name:
        traits.append(Variant(variant=output_name))

    slate_frames = (new_repre.get("data") or {}).get("slateFrames")
    if slate_frames:
        traits.append(Slate(frames=slate_frames))

    review_output_data = {
        key: new_repre[key]
        for key in REVIEW_OUTPUT_KEYS
        if new_repre.get(key) is not None
    }
    burnins = new_repre.get("burnins")
    output_def = new_repre.get("outputDef")
    if review_output_data or burnins or output_def:
        traits.append(ReviewOutput(
            burnins=list(burnins or []),
            output_def=output_def,
            **review_output_data,
        ))

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
