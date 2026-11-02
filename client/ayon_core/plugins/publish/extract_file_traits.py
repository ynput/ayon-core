"""Optional late extractor that fills in trait gaps from file inspection.

Representations are usually created during extraction, so this can't be a
collector. It runs as late as possible in the extraction phase (after every
other extractor, right before integration) and only fills traits that the
specific extractors didn't set.

This is deliberately host-agnostic Tier 1 inference only: extension/mimetype,
filename-sequence detection, and (opt-in, since it's the expensive/fragile
one) actual pixel resolution - via oiiotool for images (more reliable than
ffprobe for exr/dpx/tiff/psd/etc, and it's the tool ayon-core already uses
elsewhere for image inspection) with an ffprobe fallback for video files
and when OIIO isn't available. Anything that needs scene state or creator
intent (Spatial, SourceApplication, real colorspace, IntendedUse) belongs
in host/creator addons, not here - this plugin never invents those.

Never overwrites a trait an extractor/host already set - only fills traits
that are missing on a representation.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

import pyblish.api

from ayon_core.lib import is_oiio_supported
from ayon_core.lib.transcoding import (
    get_ffprobe_streams,
    get_oiio_info_for_input,
)
from ayon_core.pipeline.publish import (
    get_publish_instance_label,
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.traits import (
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
    PixelBased,
    Representation,
    Sequence,
    get_first_file_location,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_IMAGE_EXTS,
    DEFAULT_VIDEO_EXTS,
)
from ayon_core.pipeline.publish.trait_conversion import (
    sequence_traits_from_files,
)


def fill_mimetype_and_image(representation: Representation, log) -> None:
    """Fill missing MimeType/Image traits from the file extension alone."""
    path = get_first_file_location(representation)
    if path is None:
        return

    ext = path.suffix.lstrip(".").lower()

    if not representation.contains_trait(MimeType):
        mime_type, _ = mimetypes.guess_type(f"file.{ext}")
        if mime_type:
            representation.add_trait(MimeType(mime_type=mime_type))
            log.debug(
                f"Repre '{representation.name}': inferred MimeType"
                f" '{mime_type}' from extension."
            )

    if (
        ext in DEFAULT_IMAGE_EXTS
        and not representation.contains_trait(Image)
    ):
        representation.add_trait(Image())
        log.debug(
            f"Repre '{representation.name}': inferred Image trait from"
            " extension."
        )


def fill_sequence_from_filenames(
    representation: Representation, log
) -> None:
    """Fill missing Sequence/FrameRanged from FileLocations filenames.

    Purely a filename-pattern inference (shared with host integrations via
    `sequence_traits_from_files`) - safe and cheap, no file content is read.
    Padding, frame spec (gaps) and frame regex are derived from the files.
    """
    if not representation.contains_trait(FileLocations):
        return

    if representation.contains_trait(FrameRanged):
        return

    file_locs = representation.get_trait(FileLocations)
    if len(file_locs.file_paths) < 2:
        return

    sequence_traits = sequence_traits_from_files(
        [Path(f.file_path) for f in file_locs.file_paths]
    )
    if sequence_traits is None:
        # Files don't assemble into a single collection - not a sequence
        # we can safely describe, leave it alone.
        return

    frame_ranged, sequence = sequence_traits
    representation.add_trait(frame_ranged)
    log.debug(
        f"Repre '{representation.name}': inferred FrameRanged"
        f" {frame_ranged.frame_start}-{frame_ranged.frame_end}"
        f" (frames {sequence.frame_spec}) from filenames."
    )

    if not representation.contains_trait(Sequence):
        representation.add_trait(sequence)


def _fill_pixel_based_from_oiio(
    representation: Representation, path: Path, log
) -> bool:
    """Try filling PixelBased via oiiotool. Returns True if it did.

    Preferred for images: oiiotool reads exr/dpx/tiff/psd/etc reliably,
    where ffprobe either can't parse them at all or misreports channels
    meant for video. It's also the tool ayon-core already shells out to
    elsewhere for image inspection (see `get_oiio_info_for_input`).
    """
    if not is_oiio_supported():
        return False

    try:
        info = get_oiio_info_for_input(str(path), verbose=False, logger=log)
    except Exception:
        log.debug(
            f"Repre '{representation.name}': oiiotool failed on"
            f" '{path}', falling back to ffprobe.",
            exc_info=True,
        )
        return False

    if not info or "width" not in info or "height" not in info:
        return False

    # PixelAspectRatio is an OIIO metadata attribute, not a core ImageSpec
    # field, so it lives under attribs and may be entirely absent.
    pixel_aspect = info.get("attribs", {}).get("PixelAspectRatio", 1.0)

    representation.add_trait(PixelBased(
        display_window_width=int(info["width"]),
        display_window_height=int(info["height"]),
        pixel_aspect_ratio=float(pixel_aspect),
    ))
    log.debug(
        f"Repre '{representation.name}': inferred PixelBased"
        f" {info['width']}x{info['height']} via oiiotool."
    )
    return True


def _fill_pixel_based_from_ffprobe(
    representation: Representation, path: Path, log
) -> bool:
    """Try filling PixelBased via ffprobe. Returns True if it did.

    Fallback for video files, and for images when OIIO isn't available.
    """
    try:
        streams = get_ffprobe_streams(str(path), log)
    except Exception:
        log.debug(
            f"Repre '{representation.name}': ffprobe failed on"
            f" '{path}', skipping PixelBased inference.",
            exc_info=True,
        )
        return False

    for stream in streams:
        if "width" not in stream or "height" not in stream:
            continue
        pixel_aspect = 1.0
        # ffprobe reports sample_aspect_ratio as "num:den" when present
        sar = stream.get("sample_aspect_ratio")
        if sar and sar != "1:1" and ":" in sar:
            num, den = sar.split(":")
            try:
                if int(den) != 0:
                    pixel_aspect = int(num) / int(den)
            except ValueError:
                pass

        representation.add_trait(PixelBased(
            display_window_width=int(stream["width"]),
            display_window_height=int(stream["height"]),
            pixel_aspect_ratio=pixel_aspect,
        ))
        log.debug(
            f"Repre '{representation.name}': inferred PixelBased"
            f" {stream['width']}x{stream['height']} via ffprobe."
        )
        return True
    return False


def fill_pixel_based(representation: Representation, log) -> None:
    """Fill missing PixelBased trait by probing the file.

    This is the expensive/fragile tier - it opens the file. Gated behind
    its own settings flag (`probe_pixel_data`) separate from the cheap
    filename-only inferences above. Prefers oiiotool for image extensions,
    falls back to ffprobe (video files, or images when OIIO is missing).
    """
    if representation.contains_trait(PixelBased):
        return

    path = get_first_file_location(representation)
    if path is None or not path.exists():
        return

    ext = path.suffix.lstrip(".").lower()
    if ext not in (DEFAULT_IMAGE_EXTS | DEFAULT_VIDEO_EXTS):
        return

    if ext in DEFAULT_IMAGE_EXTS:
        if _fill_pixel_based_from_oiio(representation, path, log):
            return

    _fill_pixel_based_from_ffprobe(representation, path, log)


class ExtractFileTraits(pyblish.api.InstancePlugin):
    """Optionally fill missing traits by inspecting representation files.

    Disabled by default - this is a convenience for hosts/creators that
    don't (yet) populate every trait themselves, not a replacement for
    doing so. Never overwrites a trait that is already present.
    """

    label = "Extract File Traits"
    # As late as possible in the extraction phase - after other extractors
    # (including ExtractorOrder + 0.49 ones like ExtractColorspaceDataTraits)
    # have created/filled their representations, before integration.
    order = pyblish.api.ExtractorOrder + 0.499
    families = ["*"]

    settings_category = "core"

    enabled = False
    # Separate, opt-in flag: this one opens every file (via oiiotool for
    # images, ffprobe for video) and is meaningfully slower than the
    # filename/extension-only inferences, so it doesn't ride along with
    # `enabled` alone.
    probe_pixel_data = False
    # Opt-in per workflow - only instances with these product base types
    # are processed, nothing runs when empty.
    product_base_types = []

    def process(self, instance):
        if not self.enabled:
            return

        product_base_type = instance.data.get("productBaseType")
        if not product_base_type:
            product_base_type = instance.data["productType"]
        if product_base_type not in self.product_base_types:
            self.log.debug(
                f"Product base type \"{product_base_type}\" is not"
                " enabled for file traits, skipping."
            )
            return

        if not has_trait_representations(instance):
            return

        instance_label = get_publish_instance_label(instance)
        self.log.debug(
            f"Filling missing file traits for instance \"{instance_label}\""
        )

        for representation in get_trait_representations(instance):
            fill_mimetype_and_image(representation, self.log)
            fill_sequence_from_filenames(representation, self.log)
            if self.probe_pixel_data:
                fill_pixel_based(representation, self.log)
