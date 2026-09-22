import pyblish.api

from ayon_core.pipeline import (
    publish,
)
from ayon_core.pipeline.publish.lib import get_default_reviewable_layers
from ayon_core.lib import is_oiio_supported

from ayon_core.plugins.publish.color_transcode_utils import (
    DEFAULT_SUPPORTED_EXTS,
    TranscodeRenderer,
    apply_original_repre_disposition,
    get_profile_for_instance,
    repre_is_valid,
)


class ExtractOIIOTranscode(publish.Extractor):
    """
    Extractor to convert colors from one colorspace to different.

    Expects "colorspaceData" on representation. This dictionary is collected
    previously and denotes that representation files should be converted.
    This dict contains source colorspace information, collected by hosts.

    Target colorspace is selected by profiles in the Settings, based on:
    - host names
    - product base types
    - product names
    - task types
    - task names

    Can produce one or more representations (with different extensions) based
    on output definition in format:
        "output_name: {
            "extension": "png",
            "colorspace": "ACES - ACEScg",
            "display": "",
            "view": "",
            "tags": [],
            "custom_tags": []
        }

    If 'extension' is empty original representation extension is used.
    'output_name' will be used as name of new representation. In case of value
        'passthrough' name of original representation will be used.

    'colorspace' denotes target colorspace to be transcoded into. Could be
    empty if transcoding should be only into display and viewer colorspace.
    (In that case both 'display' and 'view' must be filled.)

    The oiiotool pipeline itself lives in
    `color_transcode_utils.TranscodeRenderer`, shared with the trait-based
    transcode extractor - this plugin only deals with legacy dict
    representations: selecting which ones to process and appending the
    results to `instance.data["representations"]`.
    """

    label = "Transcode color spaces"
    order = pyblish.api.ExtractorOrder + 0.019

    settings_category = "core"

    optional = True

    # Supported extensions
    supported_exts = set(DEFAULT_SUPPORTED_EXTS)

    # Configurable by Settings
    profiles = None
    options = None

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        if not self.profiles:
            self.log.debug("No profiles present for color transcode")
            return

        if "representations" not in instance.data:
            self.log.debug("No representations, skipping.")
            return

        if not is_oiio_supported():
            self.log.warning("OIIO not supported, no transcoding possible.")
            return

        profile = get_profile_for_instance(instance, self.profiles, self.log)
        if not profile:
            return

        profile_output_defs = profile["outputs"]
        new_representations = []
        repres = instance.data["representations"]

        scene_display = instance.data.get(
            "sceneDisplay",
            # Backward compatibility
            instance.data.get("colorspaceDisplay")
        )
        scene_view = instance.data.get(
            "sceneView",
            # Backward compatibility
            instance.data.get("colorspaceView")
        )
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)
        anatomy = instance.context.data["anatomy"]
        renderer = TranscodeRenderer(self.log, self.supported_exts)

        for idx, repre in enumerate(list(repres)):
            self.log.debug("repre ({}): `{}`".format(idx + 1, repre["name"]))
            if not repre_is_valid(
                repre, profile, self.supported_exts, self.log
            ):
                continue

            repre_new_representations, added_review = (
                renderer.render_repre_outputs(
                    instance,
                    repre,
                    profile_output_defs,
                    anatomy,
                    scene_display=scene_display,
                    scene_view=scene_view,
                    review_layers=review_layers,
                )
            )

            if repre_new_representations:
                new_representations.extend(repre_new_representations)
                repre["tags"] = apply_original_repre_disposition(
                    repre.get("tags") or [],
                    delete_original=profile["delete_original"],
                    added_review=added_review,
                )

            tags = repre.get("tags") or []
            if "delete" in tags and "thumbnail" not in tags:
                instance.data["representations"].remove(repre)

            # In case instance is not flagged for reviewable workflow
            # by `review` family we have to add it so it can be processed
            # by ExtractReview plugin
            if (
                added_review
                and "review" not in instance.data["families"]
            ):
                # TODO: Preferably we do not mess with families
                #  at this point in processing, but ExtractReview
                #  currently requires it. And this is the only way
                #  to have a representation with `review` tag
                #  actually getting picked up for non-review
                #  families.
                instance.data["families"].append("review")

        instance.data["representations"].extend(new_representations)
