"""Trait-based counterpart to `extract_colorspace_data.py`.

Fills `ColorManaged` on any trait representation that doesn't already have
it - including reviews baked by `ExtractReviewTraits`, mirroring
`ExtractColorspaceData`'s "skip if already present" behavior on the legacy
side. Runs at the same order as `ExtractColorspaceData` so both extractor
families settle colorspace data at the same point in the publish.

Reuses the existing dict-based colorspace resolution machinery
(`set_colorspace_data_to_representation` - host colorspace config lookup +
file-rule matching) through a minimal dict shim rather than reimplementing
it, same boundary-conversion approach as `extract_review_traits.py`.
"""
from __future__ import annotations

import pyblish.api

from ayon_core.pipeline.colorspace import set_colorspace_data_to_representation
from ayon_core.pipeline.publish import (
    get_publish_instance_label,
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    Representation,
    get_first_file_location,
)


def fill_colorspace_data(
    representation: Representation, context_data, log
) -> None:
    """Fill a missing `ColorManaged` trait via host colorspace file-rules.

    No-ops if the representation already has `ColorManaged`, has no file to
    inspect, or the extension/host colorspace config doesn't resolve to a
    colorspace (same conditions `set_colorspace_data_to_representation`
    already checks - see its `CachedData.allowed_exts` and "host color
    management disabled" guards).
    """
    if representation.contains_trait(ColorManaged):
        return

    path = get_first_file_location(representation)
    if path is None:
        return

    # Minimal dict shim - `set_colorspace_data_to_representation` only
    # reads "ext" and "files" and writes "colorspaceData" back onto it.
    shim = {
        "ext": path.suffix.lstrip("."),
        "files": path.name,
    }
    set_colorspace_data_to_representation(shim, context_data, log=log)

    colorspace_data = shim.get("colorspaceData")
    if not colorspace_data:
        return

    config = colorspace_data.get("config") or {}
    representation.add_trait(ColorManaged(
        color_space=colorspace_data["colorspace"],
        config_path=config.get("path"),
        config_template=config.get("template"),
    ))
    log.debug(
        f"Repre '{representation.name}': inferred ColorManaged"
        f" '{colorspace_data['colorspace']}' from host colorspace rules."
    )


class ExtractColorspaceDataTraits(pyblish.api.InstancePlugin):
    """Inject ColorManaged trait into trait representations missing it.

    Trait-based counterpart to `ExtractColorspaceData` - same order, same
    "skip if already set" semantics, same underlying colorspace resolution.
    """

    label = "Extract Colorspace data (Traits)"
    order = pyblish.api.ExtractorOrder + 0.49

    def process(self, instance):
        if not has_trait_representations(instance):
            return

        instance_label = get_publish_instance_label(instance)
        self.log.debug(
            f"Collecting colorspace data for instance \"{instance_label}\""
            " (traits)"
        )

        context_data = instance.context.data
        for representation in get_trait_representations(instance):
            fill_colorspace_data(representation, context_data, self.log)
