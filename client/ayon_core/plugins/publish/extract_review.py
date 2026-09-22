"""Legacy dict-based review extractor."""
from __future__ import annotations

import pyblish.api

from ayon_core.pipeline.publish import (
    get_publish_instance_label,
)
from ayon_core.pipeline.publish.lib import (
    add_repre_files_for_cleanup,
    get_default_reviewable_layers,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_IMAGE_EXTS,
    DEFAULT_VIDEO_EXTS,
    DEFAULT_ALPHA_EXTS,
    ReviewRenderer,
    get_profile_outputs_for_instance,
    filter_outputs_by_custom_tags,
)


class ExtractReview(pyblish.api.InstancePlugin):
    """Extracting Reviewable medias

    Compulsory attribute of representation is tags list with "review",
    otherwise the representation is ignored.

    All new representations are created and encoded by ffmpeg following
    presets found in AYON Settings interface at
    `project_settings/global/publish/ExtractReview/profiles:outputs`.

    The ffmpeg pipeline itself lives in `review_utils.ReviewRenderer`, shared
    with the trait-based review extractor - this plugin only deals with
    legacy dict representations: selecting which ones to process and
    appending the results to `instance.data["representations"]`.
    """

    label = "Extract Review"
    order = pyblish.api.ExtractorOrder + 0.02
    families = ["review"]

    settings_category = "core"
    # Supported extensions
    image_exts = set(DEFAULT_IMAGE_EXTS)
    video_exts = set(DEFAULT_VIDEO_EXTS)
    supported_exts = image_exts | video_exts

    alpha_exts = set(DEFAULT_ALPHA_EXTS)

    # Preset attributes
    profiles = []

    def process(self, instance):
        self.log.debug(str(instance.data["representations"]))
        # Skip review when requested.
        if not instance.data.get("review", True):
            return

        orig_representations = tuple(instance.data["representations"])

        # Run processing
        self.main_process(instance)

        # Make sure cleanup happens and pop representations with "delete" tag.
        for repre in orig_representations:
            tags = repre.get("tags") or []
            # Representation is not marked to be deleted
            if "delete" not in tags:
                continue

            # The representation can be used as thumbnail source
            if "thumbnail" in tags or "need_thumbnail" in tags:
                continue

            self.log.debug(
                "Removing representation: {}".format(repre)
            )
            instance.data["representations"].remove(repre)

    def _get_outputs_per_representations(self, instance, profile_outputs):
        outputs_per_representations = []
        for repre in instance.data["representations"]:
            repre_name = str(repre.get("name"))
            tags = repre.get("tags") or []
            custom_tags = repre.get("custom_tags")
            if "review" not in tags:
                self.log.debug((
                    "Repre: {} - Didn't find \"review\" in tags. Skipping"
                ).format(repre_name))
                continue

            if "thumbnail" in tags:
                self.log.debug((
                    "Repre: {} - Found \"thumbnail\" in tags. Skipping"
                ).format(repre_name))
                continue

            if "passing" in tags:
                self.log.debug((
                    "Repre: {} - Found \"passing\" in tags. Skipping"
                ).format(repre_name))
                continue

            input_ext = repre["ext"].lower()
            if input_ext.startswith("."):
                input_ext = input_ext[1:]

            if input_ext not in self.supported_exts:
                self.log.info(
                    "Representation has unsupported extension \"{}\"".format(
                        input_ext
                    )
                )
                continue

            # Filter output definition by representation's
            # custom tags (optional)
            outputs = filter_outputs_by_custom_tags(
                profile_outputs, custom_tags, self.log)
            if not outputs:
                self.log.info((
                    "Skipped representation. All output definitions from"
                    " selected profile does not match to representation's"
                    " custom tags. \"{}\""
                ).format(str(custom_tags)))
                continue

            outputs_per_representations.append((repre, outputs))
        return outputs_per_representations

    def main_process(self, instance):
        instance_label = get_publish_instance_label(instance)
        self.log.debug("Processing instance \"{}\"".format(instance_label))
        profile_outputs = get_profile_outputs_for_instance(
            instance, self.profiles, self.log
        )
        if not profile_outputs:
            return

        # Loop through representations
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
        for repre, output_defs in outputs_per_repres:
            new_repres = renderer.render_repre_outputs(
                instance, repre, output_defs, review_layers=review_layers
            )
            for new_repre in new_repres:
                self.log.debug(
                    "Adding new representation: {}".format(new_repre)
                )
                instance.data["representations"].append(new_repre)
                add_repre_files_for_cleanup(instance, new_repre)
