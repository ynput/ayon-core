"""Trait-based review extractor.

Sibling to `extract_review.py`, running the exact same ffmpeg pipeline
(`review_utils.ReviewRenderer`) but sourcing/producing trait-based
`Representation`s instead of legacy dict representations. The two never
process the same representation: this plugin only looks at
`get_trait_representations(instance)`, `ExtractReview` only looks at
`instance.data["representations"]`.

Boundary conversion (`representation_to_legacy_dict` /
`legacy_dict_to_representation`) now lives in `trait_repre_dict.py`, shared
with `extract_color_transcode_traits.py`.
"""
from __future__ import annotations

import logging

from pathlib import Path

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishError,
    get_publish_instance_label,
    has_trait_representations,
    get_trait_representations,
    add_trait_representations,
)
from ayon_core.pipeline.publish.lib import get_default_reviewable_layers
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    Representation,
    Tagged,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_ALPHA_EXTS,
    DEFAULT_IMAGE_EXTS,
    DEFAULT_VIDEO_EXTS,
    ReviewRenderer,
    filter_outputs_by_custom_tags,
    get_profile_outputs_for_instance,
    split_custom_tags,
    review_repre_tag_filter,
)
from ayon_core.plugins.publish.trait_repre_dict import (
    legacy_dict_to_representation,
    representation_to_legacy_dict,
)


def _representation_ext(representation: Representation) -> str:
    """Get lowercase extension (no dot) from a representation's files."""
    if representation.contains_trait(FileLocations):
        file_paths = representation.get_trait(FileLocations).file_paths
        if not file_paths:
            raise PublishError(
                f"Representation '{representation.name}' has an empty "
                "FileLocations trait."
            )
        path = Path(file_paths[0].file_path)
    elif representation.contains_trait(FileLocation):
        path = Path(representation.get_trait(FileLocation).file_path)
    else:
        raise PublishError(
            f"Representation '{representation.name}' has neither "
            "FileLocation nor FileLocations trait."
        )
    return path.suffix.lstrip(".").lower()


class ExtractReviewTraits(pyblish.api.InstancePlugin):
    """Extracting Reviewable medias from trait-based representations.

    Runs the same ffmpeg pipeline as `ExtractReview`
    (`review_utils.ReviewRenderer`), sourced from
    `get_trait_representations(instance)` instead of
    `instance.data["representations"]`. `profiles` is read from
    `ExtractReview`'s own settings block via `apply_settings` below (not a
    separate settings entry) - both plugins resolve the exact same
    profile/output set for equivalent instances by construction, not by
    convention.
    """

    label = "Extract Review (Traits)"
    order = pyblish.api.ExtractorOrder + 0.02
    families = ["review"]

    settings_category = "core"
    image_exts = set(DEFAULT_IMAGE_EXTS)
    video_exts = set(DEFAULT_VIDEO_EXTS)
    supported_exts = image_exts | video_exts
    alpha_exts = set(DEFAULT_ALPHA_EXTS)

    profiles = []

    log: logging.Logger

    @classmethod
    def apply_settings(cls, settings):
        # Deliberately reused from `ExtractReview`'s settings block rather
        # than a separate `ExtractReviewTraits` entry - the two plugins
        # must always resolve the same profiles for the same instance, and
        # duplicating the settings schema would let them drift.
        cls.profiles = (
            settings
            ["core"]
            ["publish"]
            ["ExtractReview"]
            ["profiles"]
        )

    def process(self, instance: pyblish.api.Instance) -> None:
        if not has_trait_representations(instance):
            return

        if not instance.data.get("review", True):
            return

        self.main_process(instance)

    def _get_outputs_per_representations(
            self,
            instance: pyblish.api.Instance,
            profile_outputs: list[dict]) -> list[tuple[Representation, list]]:
        """Get outputs per representations for the given
        instance and profile outputs.

        Args:
            instance (pyblish.api.Instance): The instance to process.
            profile_outputs (list[dict]): The profile outputs to filter.

        Returns:
            list[tuple[Representation, list]]: A list of tuples
                containing the representation and its corresponding outputs.

        """
        outputs_per_representations = []
        for representation in get_trait_representations(instance):
            tags: list[str] = []
            if representation.contains_trait(Tagged):
                tags = representation.get_trait(Tagged).tags

            should_process, skip_reason = review_repre_tag_filter(tags)
            if not should_process:
                self.log.debug(
                    f"Repre: {representation.name} - {skip_reason}. "
                    "Skipping"
                )
                continue

            ext = _representation_ext(representation)
            if ext not in self.supported_exts:
                self.log.info(
                    f"Representation has unsupported extension \"{ext}\""
                )
                continue

            # Non-control tags from the same flat Tagged.tags list stand
            # in for legacy's custom_tags, see representation_to_legacy_dict.
            outputs = filter_outputs_by_custom_tags(
                profile_outputs, split_custom_tags(tags), self.log
            )
            if not outputs:
                continue

            outputs_per_representations.append((representation, outputs))
        return outputs_per_representations

    def main_process(self, instance):
        instance_label = get_publish_instance_label(instance)
        self.log.debug(
            "Processing instance \"{}\" (traits)".format(instance_label)
        )
        profile_outputs = get_profile_outputs_for_instance(
            instance, self.profiles, self.log
        )
        if not profile_outputs:
            return

        outputs_per_repres = self._get_outputs_per_representations(
            instance, profile_outputs
        )

        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)
        renderer = ReviewRenderer(
            self.log,
            image_exts=self.image_exts,
            video_exts=self.video_exts,
            alpha_exts=self.alpha_exts,
        )

        new_trait_representations: list[Representation] = []
        for source_repre, output_defs in outputs_per_repres:
            legacy_repre = representation_to_legacy_dict(source_repre)
            new_repre_dicts = renderer.render_repre_outputs(
                instance, legacy_repre, output_defs,
                review_layers=review_layers,
            )
            for new_repre_dict in new_repre_dicts:
                new_trait_representations.append(
                    legacy_dict_to_representation(
                        new_repre_dict, source_repre
                    )
                )

        if new_trait_representations:
            self.log.debug(
                "Adding new trait representations: {}".format(
                    [r.name for r in new_trait_representations]
                )
            )
            add_trait_representations(instance, new_trait_representations)
