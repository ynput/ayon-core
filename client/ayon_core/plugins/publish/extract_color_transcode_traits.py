"""Trait-based color-transcode extractor.

Sibling to `extract_color_transcode.py`, running the exact same oiiotool
pipeline (`color_transcode_utils.TranscodeRenderer`) but sourcing/producing
trait-based `Representation`s instead of legacy dict representations. The
two never process the same representation: this plugin only looks at
`get_trait_representations(instance)`, `ExtractOIIOTranscode` only looks at
`instance.data["representations"]`.

Boundary conversion (`representation_to_legacy_dict` /
`legacy_dict_to_representation`) is shared with `extract_review_traits.py`
via `trait_repre_dict.py` - this file's only new logic is applying
`apply_original_repre_disposition` to the source representation's `Tagged`
trait and deciding which source representations survive.
"""
from __future__ import annotations

import pyblish.api

from ayon_core.lib import is_oiio_supported
from ayon_core.pipeline.publish import (
    PublishError,
    add_trait_representations,
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.publish.lib import (
    get_default_reviewable_layers,
    set_trait_representations,
)
from ayon_core.pipeline.traits import Representation, Tagged
from ayon_core.plugins.publish.color_transcode_utils import (
    DEFAULT_SUPPORTED_EXTS,
    TranscodeRenderer,
    apply_original_repre_disposition,
    get_profile_for_instance,
    repre_is_valid,
)
from ayon_core.plugins.publish.trait_repre_dict import (
    legacy_dict_to_representation,
    representation_to_legacy_dict,
)


def _get_tags(representation: Representation) -> list[str]:
    if representation.contains_trait(Tagged):
        return list(representation.get_trait(Tagged).tags)
    return []


def _set_tags(representation: Representation, tags: list[str]) -> None:
    if representation.contains_trait(Tagged):
        representation.remove_trait(Tagged)
    representation.add_trait(Tagged(tags=tags))


class ExtractOIIOTranscodeTraits(pyblish.api.InstancePlugin):
    """Convert colors from one colorspace to another, trait-based.

    Same settings profile source, same oiiotool pipeline, same
    "delete original if configured / hand off review responsibility to the
    transcoded output" bookkeeping as `ExtractOIIOTranscode` - just applied
    to `Tagged.tags` on the source `Representation` instead of a dict's
    "tags" key, and to the instance's trait-representation list instead of
    `instance.data["representations"]`.
    """

    label = "Transcode color spaces (Traits)"
    order = pyblish.api.ExtractorOrder + 0.019

    settings_category = "core"

    optional = True
    supported_exts = set(DEFAULT_SUPPORTED_EXTS)

    profiles = None

    @classmethod
    def apply_settings(cls, settings):
        # Deliberately reused from `ExtractOIIOTranscode`'s settings block,
        # same reasoning as `ExtractReviewTraits.apply_settings`: the two
        # plugins must resolve identical profiles, never a separate entry
        # that could drift.
        transcode_settings = (
            settings
            ["core"]
            ["publish"]
            ["ExtractOIIOTranscode"]
        )
        cls.profiles = transcode_settings["profiles"]
        cls.optional = transcode_settings.get("optional", cls.optional)

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        if not self.profiles:
            self.log.debug("No profiles present for color transcode")
            return

        if not has_trait_representations(instance):
            return

        if not is_oiio_supported():
            self.log.warning("OIIO not supported, no transcoding possible.")
            return

        self.main_process(instance)

    def main_process(self, instance):
        profile = get_profile_for_instance(instance, self.profiles, self.log)
        if not profile:
            return

        profile_output_defs = profile["outputs"]
        scene_display = instance.data.get(
            "sceneDisplay", instance.data.get("colorspaceDisplay")
        )
        scene_view = instance.data.get(
            "sceneView", instance.data.get("colorspaceView")
        )
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)
        anatomy = instance.context.data["anatomy"]
        renderer = TranscodeRenderer(self.log, self.supported_exts)

        existing_repres = list(get_trait_representations(instance))
        kept_repres: list[Representation] = []
        new_trait_representations: list[Representation] = []
        added_review_overall = False

        for source_repre in existing_repres:
            try:
                legacy_repre = representation_to_legacy_dict(source_repre)
            except PublishError as exc:
                self.log.debug(
                    f"Repre '{source_repre.name}' can't be converted for"
                    f" transcoding: {exc}. Skipping."
                )
                kept_repres.append(source_repre)
                continue

            if not repre_is_valid(
                legacy_repre, profile, self.supported_exts, self.log
            ):
                kept_repres.append(source_repre)
                continue

            repre_new_dicts, added_review = renderer.render_repre_outputs(
                instance,
                legacy_repre,
                profile_output_defs,
                anatomy,
                scene_display=scene_display,
                scene_view=scene_view,
                review_layers=review_layers,
            )

            if repre_new_dicts:
                for new_repre_dict in repre_new_dicts:
                    new_trait_representations.append(
                        legacy_dict_to_representation(
                            new_repre_dict, source_repre
                        )
                    )
                _set_tags(
                    source_repre,
                    apply_original_repre_disposition(
                        _get_tags(source_repre),
                        delete_original=profile["delete_original"],
                        added_review=added_review,
                    ),
                )

            if added_review:
                added_review_overall = True

            tags = _get_tags(source_repre)
            if "delete" in tags and "thumbnail" not in tags:
                # Dropped, same as legacy's
                # `instance.data["representations"].remove(repre)`.
                continue

            kept_repres.append(source_repre)

        if new_trait_representations or len(kept_repres) != len(
            existing_repres
        ):
            set_trait_representations(
                instance, kept_repres + new_trait_representations
            )

        # See ExtractOIIOTranscode's TODO on the same line: ExtractReview
        # (and its trait counterpart) currently require the "review"
        # family to pick up a representation with a "review" tag.
        if (
            added_review_overall
            and "review" not in instance.data["families"]
        ):
            instance.data["families"].append("review")
