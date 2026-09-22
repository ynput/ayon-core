"""Boundary conversion between trait `Representation` and the internal
dict-repre DTO shape shared publish-pipeline code (`ReviewRenderer`,
`TranscodeRenderer`) still operates on.

Originally lived only in `extract_review_traits.py`; generalized here once
`extract_color_transcode_traits.py` needed the exact same shape plus
`colorspaceData` round-tripping. Both trait extractors import these two
functions rather than keeping their own copies - this is the *only* place
that translates between the two representation models.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from ayon_core.pipeline.publish import PublishError
from ayon_core.pipeline.traits import (
    ColorManaged,
    FileLocation,
    FileLocations,
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
    split_custom_tags,
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
        # `Tagged` is a single flat tag list on traits, unlike legacy's
        # split "tags" (review/thumbnail/passing/control tags) vs
        # "custom_tags" (arbitrary output-matching tags). Strip the known
        # control tags so a representation's mandatory "review" tag doesn't
        # masquerade as a custom tag - see split_custom_tags.
        "custom_tags": split_custom_tags(tags),
    }

    if representation.contains_trait(ColorManaged):
        cm = representation.get_trait(ColorManaged)
        result["colorspaceData"] = {
            "colorspace": cm.color_space,
            "config": {
                "path": cm.config_path,
                "template": cm.config_template,
            },
        }

    return result


def legacy_dict_to_representation(
    new_repre: dict[str, Any],
    source: Representation,
) -> Representation:
    """Convert one renderer-output dict back into a Representation.

    If `new_repre` carries `colorspaceData` (set or updated by the shared
    renderer, e.g. `TranscodeRenderer` changing the target colorspace),
    that becomes the result's `ColorManaged` trait. Otherwise `ColorManaged`
    is carried over unchanged from `source` (the common case - most
    renderers, e.g. `ReviewRenderer`, never touch color).

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
        try:
            frame_ranged = FileLocations.get_sequence_from_files(
                [staging_dir / filename for filename in files]
            )
        except ValueError:
            pass
        else:
            if new_repre.get("fps"):
                frame_ranged.frames_per_second = str(new_repre["fps"])
            traits.append(frame_ranged)
            traits.append(Sequence(
                frame_padding=len(str(frame_ranged.frame_end))
            ))
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

    tags = new_repre.get("tags") or []
    traits.append(Tagged(tags=tags))

    colorspace_data = new_repre.get("colorspaceData")
    if colorspace_data:
        config = colorspace_data.get("config") or {}
        traits.append(ColorManaged(
            color_space=colorspace_data["colorspace"],
            config_path=config.get("path"),
            config_template=config.get("template"),
        ))
    elif source.contains_trait(ColorManaged):
        traits.append(source.get_trait(ColorManaged))

    if "delete" not in tags:
        traits.append(Persistent())

    return Representation(name=new_repre["name"], traits=traits)
