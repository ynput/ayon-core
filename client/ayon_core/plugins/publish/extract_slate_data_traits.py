"""Trait-based variant of `extract_slate_data.py`."""
import pyblish.api

from ayon_core.pipeline.publish import (
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.traits import Slate, Tagged


class ExtractSlateDataTraits(pyblish.api.InstancePlugin):
    """Add slate trait to trait-based representations with slate frame.

    Integration stores the slate frames to representation data as well.
    """

    label = "Slate Data (Traits)"
    # Offset from ExtractReviewSlate and ExtractGenerateSlate.
    order = pyblish.api.ExtractorOrder + 0.49
    families = ["slate", "review"]
    hosts = ["nuke", "shell"]

    def process(self, instance):
        if not has_trait_representations(instance):
            return

        for representation in get_trait_representations(instance):
            if representation.contains_trait(Slate):
                continue
            if not representation.contains_trait(Tagged):
                continue
            if "slate-frame" not in representation.get_trait(Tagged).tags:
                continue
            representation.add_trait(Slate(frames=1))
