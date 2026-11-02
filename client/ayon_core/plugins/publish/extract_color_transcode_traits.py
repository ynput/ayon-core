"""Trait-based color-transcode extractor.

Sibling to `extract_color_transcode.py` working on trait representations.
The two never process the same representation: this plugin only looks at
`get_trait_representations(instance)`, `ExtractOIIOTranscode` only looks at
`instance.data["representations"]`.

Source colorspace and OCIO config are read from the `ColorManaged` trait.
Each output is a copy of the source representation pointing to
the transcoded files with updated `ColorManaged` trait.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Optional

import clique
import pyblish.api

from ayon_core.lib import is_oiio_supported
from ayon_core.lib.transcoding import (
    MissingRGBAChannelsError,
    oiio_color_convert,
)
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish import (
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.publish.lib import (
    get_default_reviewable_layers,
    set_trait_representations,
)
from ayon_core.pipeline.publish.trait_utils import (
    copy_representation,
    get_ext,
    get_file_paths,
    get_ocio_config_path,
    get_tags,
    has_files,
    set_files,
    set_staging_directory,
    set_tags,
    set_variant,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    CustomTags,
    Representation,
)
from ayon_core.plugins.publish.color_transcode_utils import (
    DEFAULT_SUPPORTED_EXTS,
    apply_original_repre_disposition,
    get_profile_for_instance,
)


def _get_output_filenames(
        filenames: list[str], output_extension: str) -> list[str]:
    """Get file names of transcoded files (with the output extension)."""
    if not output_extension:
        return list(filenames)
    return [
        f"{os.path.splitext(filename)[0]}.{output_extension}"
        for filename in filenames
    ]


def _get_conversion_inputs(
    filenames: list[str],
) -> list[tuple[str, Optional[str], Optional[int]]]:
    """Get inputs for oiiotool - sequence pattern or single files.

    Returns:
        list[tuple[str, Optional[str], Optional[int]]]: File name (with
            "#" frame pattern for sequence), frames and frame padding.

    """
    collections, _ = clique.assemble(
        filenames,
        patterns=[clique.PATTERNS["frames"]],
        assume_padded_when_ambiguous=True,
    )
    if not collections:
        return [(filename, None, None) for filename in filenames]
    if len(collections) > 1:
        msg = f"Too many collections {collections}"
        raise ValueError(msg)
    collection = collections[0]
    return [(
        collection.format("{head}#{tail}"),
        collection.format("{ranges}").replace(" ", ""),
        collection.padding,
    )]


class ExtractOIIOTranscodeTraits(pyblish.api.InstancePlugin):
    """Convert colors from one colorspace to another, trait-based.

    Same settings profile source, same oiiotool conversion, same
    "delete original if configured / hand off review responsibility to the
    transcoded output" bookkeeping as `ExtractOIIOTranscode`.
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

        existing_repres = list(get_trait_representations(instance))
        kept_repres: list[Representation] = []
        new_trait_representations: list[Representation] = []
        added_review_overall = False

        for source in existing_repres:
            if not self._is_valid(source, profile):
                kept_repres.append(source)
                continue

            outputs, added_review = self._transcode(
                instance, source, profile["outputs"]
            )
            if outputs:
                new_trait_representations.extend(outputs)
                set_tags(source, apply_original_repre_disposition(
                    get_tags(source),
                    delete_original=profile["delete_original"],
                    added_review=added_review,
                ))

            if added_review:
                added_review_overall = True

            tags = get_tags(source)
            if "delete" in tags and "thumbnail" not in tags:
                # Dropped, same as legacy's
                # `instance.data["representations"].remove(repre)`.
                continue

            kept_repres.append(source)

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

    def _is_valid(self, representation: Representation, profile: dict) -> bool:
        """Check whether representation should be transcoded by profile."""
        if not has_files(representation):
            self.log.debug(
                f"Representation '{representation.name}' has empty files."
                " Skipped."
            )
            return False

        ext = get_ext(representation)
        if ext not in self.supported_exts:
            self.log.debug(
                f"Representation '{representation.name}' has unsupported"
                f" extension: '{ext}'. Skipped."
            )
            return False

        if not representation.contains_trait(ColorManaged):
            self.log.debug(
                f"Representation '{representation.name}' is not color"
                " managed. Skipped."
            )
            return False

        representations_names = profile["representation_names"]
        if not representations_names:
            return True
        return any(
            re.match(pattern, representation.name)
            for pattern in representations_names
        )

    def _transcode(
        self,
        instance: pyblish.api.Instance,
        source: Representation,
        output_defs: list[dict],
    ) -> tuple[list[Representation], bool]:
        """Transcode source representation by all output definitions.

        Returns:
            tuple[list[Representation], bool]: New representations and
                whether any output (or the source) is tagged "review".

        """
        anatomy = instance.context.data["anatomy"]
        source_color = source.get_trait(ColorManaged)
        config_path = get_ocio_config_path(
            source_color, anatomy, logger=self.log
        )
        if not config_path:
            self.log.debug(
                "Skipping OIIO Color Transcode because no OCIO config"
                " path found on representation."
            )
            return [], False

        scene_display = instance.data.get(
            "sceneDisplay", instance.data.get("colorspaceDisplay")
        )
        scene_view = instance.data.get(
            "sceneView", instance.data.get("colorspaceView")
        )
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)

        source_paths = get_file_paths(source)
        source_dir = source_paths[0].parent
        filenames = [path.name for path in source_paths]
        source_tags = get_tags(source)

        outputs: list[Representation] = []
        added_review = False
        for output_def in output_defs:
            output_name = output_def["name"]
            output_extension = output_def["extension"].replace(".", "")
            output_dir = get_temp_dir(
                project_name=instance.context.data["projectName"],
                use_local_temp=True,
            )

            target_colorspace = target_view = target_display = None
            transcoding_type = output_def["transcoding_type"]
            if transcoding_type == "colorspace":
                target_colorspace = output_def["colorspace"]
            elif transcoding_type == "display_view":
                display_view = output_def["display_view"]
                target_view = display_view["view"] or scene_view
                target_display = display_view["display"] or scene_display

            additional_command_args = (
                output_def["oiiotool_args"]["additional_command_args"]
            )
            conversion_inputs = _get_conversion_inputs(filenames)
            self.log.debug(f"Files to convert: {conversion_inputs}")
            converted = True
            for filename, frames, frame_padding in conversion_inputs:
                self.log.debug(f"Transcoding file: `{filename}`")
                input_path = os.path.join(source_dir, filename)
                output_path = os.path.join(
                    output_dir,
                    _get_output_filenames([filename], output_extension)[0],
                )
                try:
                    oiio_color_convert(
                        input_path=input_path,
                        output_path=output_path,
                        config_path=config_path,
                        source_colorspace=source_color.color_space,
                        target_colorspace=target_colorspace,
                        target_display=target_display,
                        target_view=target_view,
                        source_display=source_color.display,
                        source_view=source_color.view,
                        additional_command_args=additional_command_args,
                        frames=frames,
                        frame_padding=frame_padding,
                        parallel_frames=frames is not None,
                        review_layers=review_layers,
                        logger=self.log,
                    )
                except MissingRGBAChannelsError as exc:
                    converted = False
                    self.log.error(exc)
                    self.log.error(
                        "Skipping OIIO Transcode. Unknown RGBA channels"
                        f" for colorspace conversion in file: {input_path}"
                    )
                    break

            if not converted:
                # Stop processing remaining output defs for this source.
                break

            output_paths = [
                Path(output_dir) / filename
                for filename in _get_output_filenames(
                    filenames, output_extension)
            ]
            for path in output_paths:
                instance.context.data["cleanupFullPaths"].append(str(path))

            name = source.name
            if output_name != "passthrough":
                name = output_name
            representation = copy_representation(source, name=name)
            if output_extension:
                set_variant(representation, output_name)
            set_files(
                representation,
                output_paths,
                sequence=len(output_paths) > 1,
            )
            set_staging_directory(representation, Path(output_dir))

            color_managed = copy.deepcopy(source_color)
            if target_view:
                color_managed.view = target_view
            if target_display:
                color_managed.display = target_display
            if target_colorspace:
                color_managed.color_space = target_colorspace
            representation.remove_trait(ColorManaged)
            representation.add_trait(color_managed)

            custom_tags = output_def.get("custom_tags")
            if custom_tags:
                existing_custom_tags = []
                if representation.contains_trait(CustomTags):
                    existing_custom_tags = representation.get_trait(
                        CustomTags).tags
                    representation.remove_trait(CustomTags)
                representation.add_trait(CustomTags(
                    tags=[*existing_custom_tags, *custom_tags]
                ))

            tags = list(source_tags)
            for tag in output_def["tags"]:
                if tag not in tags:
                    tags.append(tag)
                if tag == "review":
                    added_review = True
            set_tags(representation, tags)
            update_persistence(representation)

            if "review" in source_tags:
                added_review = True

            outputs.append(representation)

        return outputs, added_review
