"""Shared OIIO color-transcode logic used by both the legacy dict-based
extractor (`extract_color_transcode.py`) and the trait-based one
(`extract_color_transcode_traits.py`).

Same split as `review_utils.py`: `TranscodeRenderer` is a behavior-preserving
lift of `ExtractOIIOTranscode`'s per-representation/per-output logic out of
the pyblish plugin class, operating on a plain repre dict in/out (including
`colorspaceData`) so both extractors run the exact same oiiotool pipeline.
"""
from __future__ import annotations

import os
import re
import copy
from typing import Optional

import clique

from ayon_core.lib import filter_profiles
from ayon_core.lib.transcoding import MissingRGBAChannelsError, oiio_color_convert
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.colorspace import get_representation_ocio_config_path

DEFAULT_SUPPORTED_EXTS = {"exr", "jpg", "jpeg", "png", "dpx", "tif", "tiff"}


def get_profile_for_instance(
    instance, profiles, log
) -> Optional[dict]:
    """Resolve the settings profile for one instance.

    Matches on host/product-base-type/product-name/task-name/task-type -
    a different (finer-grained) filter set than review's `filter_profiles`
    call, since transcode profiles target specific products/tasks rather
    than families. Shared unmodified by both extractors: nothing here reads
    representation data.
    """
    host_name = instance.context.data["hostName"]
    product_base_type = instance.data.get("productBaseType")
    if not product_base_type:
        product_base_type = instance.data["productType"]
    product_name = instance.data["productName"]
    task_data = instance.data["anatomyData"].get("task", {})
    task_name = task_data.get("name")
    task_type = task_data.get("type")
    filtering_criteria = {
        "host_names": host_name,
        "product_base_types": product_base_type,
        "product_names": product_name,
        "task_names": task_name,
        "task_types": task_type,
    }
    profile = filter_profiles(profiles, filtering_criteria, logger=log)

    if not profile:
        log.debug(
            "Skipped instance. None of profiles in presets are for"
            f" Host name: \"{host_name}\""
            f" | Product base type: \"{product_base_type}\""
            f" | Product name: \"{product_name}\""
            f" | Task name \"{task_name}\""
            f" | Task type \"{task_type}\""
        )

    return profile


def repre_is_valid(
    repre: dict, profile: dict, supported_exts, log
) -> bool:
    """Validate whether a repre dict should be processed by this profile.

    Shared by both extractors - operates on the same DTO shape either way.
    """
    if repre.get("ext") not in supported_exts:
        log.debug(
            f"Representation '{repre.get('name')}' has unsupported"
            f" extension: '{repre.get('ext')}'. Skipped."
        )
        return False

    if not repre.get("files"):
        log.debug(
            f"Representation '{repre.get('name')}' has empty files."
            " Skipped."
        )
        return False

    if not repre.get("colorspaceData"):
        log.debug(
            f"Representation '{repre.get('name')}' has no colorspace"
            " data. Skipped."
        )
        return False

    representations_names = profile["representation_names"]
    if not representations_names:
        return True

    repre_name = repre["name"]
    for r_pattern in representations_names:
        if re.match(r_pattern, repre_name):
            return True

    return False


def apply_original_repre_disposition(
    tags: list[str], *, delete_original: bool, added_review: bool
) -> list[str]:
    """Pure tag-list transform mirroring
    `ExtractOIIOTranscode._mark_original_repre_for_deletion`.

    Adds "delete" if the profile says to delete the original, removes
    "review" if a transcoded output took over the review responsibility.
    Shared by both extractors - each applies it to whatever holds their
    source's tags (dict `repre["tags"]` vs trait `Tagged.tags`).
    """
    new_tags = list(tags)
    if delete_original and "delete" not in new_tags:
        new_tags.append("delete")
    if added_review and "review" in new_tags:
        new_tags.remove("review")
    return new_tags


def _rename_in_representation(
    new_repre, files_to_convert, output_name, output_extension
):
    """Replace old extension with new one everywhere in representation."""
    if output_name != "passthrough":
        new_repre["name"] = output_name
    if not output_extension:
        return

    new_repre["ext"] = output_extension
    new_repre["outputName"] = output_name

    renamed_files = []
    for file_name in files_to_convert:
        file_name, _ = os.path.splitext(file_name)
        file_name = "{}.{}".format(file_name, output_extension)
        renamed_files.append(file_name)
    new_repre["files"] = renamed_files


def _translate_to_sequence(files_to_convert):
    """Returns original individual filepaths or list of clique.Collection."""
    pattern = [clique.PATTERNS["frames"]]
    collections, _ = clique.assemble(
        files_to_convert, patterns=pattern,
        assume_padded_when_ambiguous=True)
    if collections:
        if len(collections) > 1:
            raise ValueError("Too many collections {}".format(collections))
        return collections
    return files_to_convert


def _get_output_file_path(input_path, output_dir, output_extension):
    """Create output file name path."""
    file_name = os.path.basename(input_path)
    file_name, input_extension = os.path.splitext(file_name)
    if not output_extension:
        output_extension = input_extension.replace(".", "")
    new_file_name = "{}.{}".format(file_name, output_extension)
    return os.path.join(output_dir, new_file_name)


class TranscodeRenderer:
    """Runs the OIIO color-transcode pipeline for output definitions.

    Lifted from `ExtractOIIOTranscode` verbatim; only entry/exit points
    changed from "mutate instance.data in place" to "return new repre
    dicts + whether any output claimed the review responsibility".
    """

    def __init__(self, log, supported_exts=None):
        self.log = log
        self.supported_exts = supported_exts or set(DEFAULT_SUPPORTED_EXTS)

    def render_repre_outputs(
        self,
        instance,
        repre: dict,
        profile_output_defs: list[dict],
        anatomy,
        scene_display=None,
        scene_view=None,
        review_layers=None,
    ) -> tuple[list[dict], bool]:
        """Transcode one source `repre` dict through all `profile_output_defs`.

        Returns:
            tuple[list[dict], bool]: (new repre dicts, added_review) -
                `added_review` is True if any produced output (or the
                source itself) carries the "review" tag, matching legacy's
                bookkeeping for whether the "review" family needs adding.

        """
        colorspace_data = repre["colorspaceData"]
        config_path = get_representation_ocio_config_path(
            repre, anatomy=anatomy, logger=self.log
        )
        if not config_path:
            self.log.debug(
                "Skipping OIIO Color Transcode because no OCIO config"
                " path found on representation."
            )
            return [], False

        source_colorspace = colorspace_data["colorspace"]
        source_display = colorspace_data.get("display")
        source_view = colorspace_data.get("view")

        if isinstance(repre["files"], list):
            repre_files_to_convert = copy.deepcopy(repre["files"])
        else:
            repre_files_to_convert = [repre["files"]]

        new_representations: list[dict] = []
        added_review = False

        original_staging_dir = repre["stagingDir"]

        for output_def in profile_output_defs:
            files_to_convert = list(repre_files_to_convert)

            output_name = output_def["name"]
            new_repre = copy.deepcopy(repre)

            new_staging_dir = get_temp_dir(
                project_name=instance.context.data["projectName"],
                use_local_temp=True,
            )
            new_repre["stagingDir"] = new_staging_dir

            output_extension = output_def["extension"].replace(".", "")
            _rename_in_representation(
                new_repre, files_to_convert, output_name, output_extension
            )

            transcoding_type = output_def["transcoding_type"]
            target_colorspace = target_view = target_display = None
            if transcoding_type == "colorspace":
                target_colorspace = output_def["colorspace"]
            elif transcoding_type == "display_view":
                display_view = output_def["display_view"]
                target_view = display_view["view"] or scene_view
                target_display = display_view["display"] or scene_display

            if target_view:
                new_repre["colorspaceData"]["view"] = target_view
            if target_display:
                new_repre["colorspaceData"]["display"] = target_display
            if target_colorspace:
                new_repre["colorspaceData"]["colorspace"] = target_colorspace

            additional_command_args = (
                output_def["oiiotool_args"]["additional_command_args"]
            )

            sequence_files = _translate_to_sequence(files_to_convert)
            self.log.debug("Files to convert: {}".format(sequence_files))
            missing_rgba_review_channels = False
            for file_name in sequence_files:
                if isinstance(file_name, clique.Collection):
                    frames = file_name.format("{ranges}").replace(" ", "")
                    frame_padding = file_name.padding
                    file_name = file_name.format("{head}#{tail}")
                    parallel_frames = True
                elif isinstance(file_name, str):
                    frames = None
                    frame_padding = None
                    parallel_frames = False
                else:
                    raise TypeError(
                        f"Unsupported file name type: {type(file_name)}."
                        " Expected str or clique.Collection."
                    )

                self.log.debug("Transcoding file: `{}`".format(file_name))
                input_path = os.path.join(original_staging_dir, file_name)
                output_path = _get_output_file_path(
                    input_path, new_staging_dir, output_extension
                )
                try:
                    oiio_color_convert(
                        input_path=input_path,
                        output_path=output_path,
                        config_path=config_path,
                        source_colorspace=source_colorspace,
                        target_colorspace=target_colorspace,
                        target_display=target_display,
                        target_view=target_view,
                        source_display=source_display,
                        source_view=source_view,
                        additional_command_args=additional_command_args,
                        frames=frames,
                        frame_padding=frame_padding,
                        parallel_frames=parallel_frames,
                        review_layers=review_layers,
                        logger=self.log,
                    )
                except MissingRGBAChannelsError as exc:
                    missing_rgba_review_channels = True
                    self.log.error(exc)
                    self.log.error(
                        "Skipping OIIO Transcode. Unknown RGBA channels"
                        f" for colorspace conversion in file: {input_path}"
                    )
                    break

            if missing_rgba_review_channels:
                # Stop processing remaining output defs for this repre.
                break

            for file_name in new_repre["files"]:
                transcoded_file_path = os.path.join(
                    new_staging_dir, file_name
                )
                instance.context.data["cleanupFullPaths"].append(
                    transcoded_file_path
                )

            custom_tags = output_def.get("custom_tags")
            if custom_tags:
                if new_repre.get("custom_tags") is None:
                    new_repre["custom_tags"] = []
                new_repre["custom_tags"].extend(custom_tags)

            if new_repre.get("tags") is None:
                new_repre["tags"] = []
            for tag in output_def["tags"]:
                if tag not in new_repre["tags"]:
                    new_repre["tags"].append(tag)
                if tag == "review":
                    added_review = True

            if len(new_repre["files"]) == 1:
                new_repre["files"] = new_repre["files"][0]

            if "review" in (repre.get("tags") or []):
                added_review = True

            new_representations.append(new_repre)

        return new_representations, added_review
