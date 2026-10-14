"""Trait-based review extractor.

Sibling to `extract_review.py`, running the same ffmpeg pipeline
(`review_utils.ReviewRenderer`) on trait-based `Representation`s instead
of legacy dict representations. The two never process the same
representation: this plugin only looks at
`get_trait_representations(instance)`, `ExtractReview` only looks at
`instance.data["representations"]`.

Source files, frame range, tags and output name are read from traits of
the source representation and outputs are created as new trait
representations. Data needed by the following plugins (linked burnins,
ffmpeg command, output definition) are passed in the non-persistent
`ReviewOutput` trait.
"""
from __future__ import annotations

import copy
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

import clique
import pyblish.api

from ayon_core.lib import run_subprocess
from ayon_core.lib.transcoding import (
    convert_input_paths_for_ffmpeg,
    get_review_layer_name,
    should_convert_for_ffmpeg,
)
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish import (
    PublishError,
    add_trait_representation_files_for_cleanup,
    add_trait_representations,
    get_publish_instance_label,
    get_trait_representations,
    has_trait_representations,
)
from ayon_core.pipeline.publish.lib import (
    fill_sequence_gaps_with_previous_version,
    get_default_reviewable_layers,
)
from ayon_core.pipeline.publish.review_utils import (
    DEFAULT_ALPHA_EXTS,
    DEFAULT_IMAGE_EXTS,
    DEFAULT_VIDEO_EXTS,
    ReviewRenderer,
    TempData,
    filter_outputs_by_custom_tags,
    frame_to_timecode,
    get_profile_outputs_for_instance,
    review_repre_tag_filter,
    single_frame_filter,
)
from ayon_core.pipeline.publish.trait_utils import (
    copy_representation,
    get_ext,
    get_file_paths,
    get_tags,
    get_variant,
    is_sequence,
    set_files,
    set_staging_directory,
    set_tags,
    set_variant,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    CustomTags,
    FrameRangeData,
    FrameRanged,
    Handles,
    PixelBased,
    Representation,
    ReviewOutput,
    Slate,
    StagingDirectory,
    get_frame_range_data,
)

# traits of the source representation describing also the review output
#   - output is staged next to the source, it keeps persistence of
#   the source staging directory
OUTPUT_TRAITS_FROM_SOURCE = (ColorManaged, CustomTags, Slate, StagingDirectory)


class TraitTempData(TempData):
    """`TempData` with source files of a trait representation.

    `origin_repre` of `TempData` is not used, source files are in
    `input_dir` and `input_files`.
    """
    input_dir: str
    input_files: list[str]


class _OutputFiles:
    """Files and resolution of review output being rendered.

    Note:
        Not a dataclass - pyblish loads plugin files without registering
            them as modules, which dataclasses require.

    """
    def __init__(self, tags: list[str], staging_dir: str) -> None:
        self.tags = tags
        self.staging_dir = staging_dir
        self.ext = ""
        self.files: list[str] = []
        self.is_sequence = False
        self.resolution: Optional[tuple[int, int]] = None
        self.source_resolution: Optional[tuple[int, int]] = None


def _add_output_frame_traits(
        representation: Representation,
        frame_range: FrameRangeData,
        output_def: dict) -> None:
    """Add frame range traits to review output.

    Output contains the content frame range of the source with handles,
    unless output definition is tagged "no-handles", and slate frames
    if the output has `Slate` trait. Traits created from the output files
    (sequence outputs) are kept.

    Args:
        representation (Representation): Review output representation.
        frame_range (FrameRangeData): Frame range of the source.
        output_def (dict): Output definition used for the output.

    """
    if representation.contains_trait(FrameRanged):
        return

    handle_start = frame_range.handle_start
    handle_end = frame_range.handle_end
    if "no-handles" in (output_def.get("tags") or []):
        handle_start = handle_end = 0

    slate_frames = 0
    if representation.contains_trait(Slate):
        slate_frames = representation.get_trait(Slate).frames

    frame_ranged = FrameRanged(
        frame_start=(
            frame_range.content_frame_start - handle_start - slate_frames
        ),
        frame_end=frame_range.content_frame_end + handle_end,
    )
    frame_ranged.frame_rate = frame_range.frame_rate
    representation.add_trait(frame_ranged)
    representation.add_trait(Handles(
        inclusive=True,
        frame_start_handle=handle_start,
        frame_end_handle=handle_end,
    ))


class TraitReviewRenderer(ReviewRenderer):
    """Review ffmpeg pipeline for trait representations.

    Uses ffmpeg arguments preparation of `ReviewRenderer`. Source files,
    frame range and tags are read from traits and outputs are created
    as trait representations.
    """

    def render_representation(
        self,
        instance: pyblish.api.Instance,
        source: Representation,
        output_defs: list[dict],
        review_layers: list[str],
    ) -> list[Representation]:
        """Render all output definitions for a source representation.

        Args:
            instance (pyblish.api.Instance): Publish instance.
            source (Representation): Source representation.
            output_defs (list[dict]): Output definitions.
            review_layers (list[str]): Reviewable layers.

        Returns:
            list[Representation]: New review representations. Empty if
                the source was skipped.

        """
        input_paths = [str(path) for path in get_file_paths(source)]
        filtered_output_defs = single_frame_filter(input_paths, output_defs)
        if not filtered_output_defs:
            self.log.debug(
                f"Repre: {source.name} - All output definitions were"
                " filtered out by single frame filter. Skipped."
            )
            return []

        first_input_path = input_paths[0]
        do_convert = should_convert_for_ffmpeg(
            first_input_path, review_layers=review_layers
        )
        if do_convert is None:
            self.log.info(
                "Can't determine if representation requires conversion."
                " Skipped."
            )
            return []

        layer_name = get_review_layer_name(
            first_input_path, review_layers=review_layers
        )
        source_dir = os.path.dirname(first_input_path)
        input_dir = source_dir
        if do_convert:
            input_dir = get_temp_dir(
                project_name=instance.context.data["projectName"],
                use_local_temp=True,
            )
            convert_input_paths_for_ffmpeg(
                input_paths,
                input_dir,
                review_layers=review_layers,
                logger=self.log,
            )
            # The OIIO conversion will remap the RGBA channels just to
            # `R,G,B,A` so we will pass the intermediate file to FFMPEG
            # without layer name.
            layer_name = ""

        try:
            return [
                output
                for output_def in filtered_output_defs
                for output in self._render_output(
                    instance,
                    source,
                    input_dir,
                    source_dir,
                    output_def,
                    layer_name,
                )
            ]
        finally:
            if do_convert and os.path.exists(input_dir):
                shutil.rmtree(input_dir)

    def _render_output(
        self,
        instance: pyblish.api.Instance,
        source: Representation,
        input_dir: str,
        source_dir: str,
        _output_def: dict,
        layer_name: str,
    ) -> list[Representation]:
        """Render one output definition.

        Returns:
            list[Representation]: Created representation or empty list if
                output could not be created.

        """
        output_def = copy.deepcopy(_output_def)
        output_def.setdefault("tags", [])
        output_def.setdefault("burnins", [])

        tags = [
            tag
            for tag in get_tags(source)
            if tag not in ("delete", "need_thumbnail")
        ]
        for tag in output_def["tags"]:
            if tag not in tags:
                tags.append(tag)

        burnins = []
        if source.contains_trait(ReviewOutput):
            burnins = list(source.get_trait(ReviewOutput).burnins)
        for burnin in output_def["burnins"]:
            if str(burnin) not in burnins:
                burnins.append(str(burnin))
        self.log.debug(f"Linked burnins: `{burnins}`")
        self.log.debug(f"New representation tags: `{tags}`")

        frame_range = get_frame_range_data(source)
        temp_data = self.prepare_trait_temp_data(
            instance, source, input_dir, output_def, frame_range
        )
        output_files = _OutputFiles(tags=tags, staging_dir=source_dir)

        new_frame_files = {}
        if temp_data.input_is_sequence:
            new_frame_files = self._fill_sequence_gaps(
                instance, source, source_dir, _output_def, temp_data
            )
        temp_data.filled_files = new_frame_files

        output_name = get_variant(source)
        if output_name:
            output_name += "_"
        output_name += output_def["filename_suffix"]
        if temp_data.without_handles:
            output_name += "_noHandles"

        source_ext = get_ext(source)
        fill_data = copy.deepcopy(instance.data["anatomyData"])
        fill_data.update({
            "output": output_name,
            "ext": source_ext,
            "timecode": frame_to_timecode(
                frame=temp_data.frame_start_handle,
                fps=temp_data.fps,
            )
        })

        try:  # temporary until oiiotool is supported cross platform
            ffmpeg_args = self._ffmpeg_arguments(
                output_def,
                instance,
                output_files,
                temp_data,
                fill_data,
                layer_name,
            )
        except ZeroDivisionError:
            # TODO recalculate width and height using OIIO before
            #   conversion
            if temp_data.input_ext.lower() == "exr":
                self.log.warning(
                    "Unsupported compression on input files. Skipping!!!",
                    exc_info=True
                )
                return []
            raise NotImplementedError

        subprcs_cmd = " ".join(ffmpeg_args)
        self.log.debug(f"Executing: {subprcs_cmd}")
        run_subprocess(subprcs_cmd, shell=True, logger=self.log)

        for filepath in new_frame_files.values():
            os.unlink(filepath)
        for filepath in temp_data.paths_to_remove:
            os.unlink(filepath)

        # Name is unique by output name and extension of the source
        representation = copy_representation(
            source,
            name=f"{output_name}_{source_ext}",
            traits=list(OUTPUT_TRAITS_FROM_SOURCE),
        )
        set_tags(representation, tags)
        set_staging_directory(representation, Path(output_files.staging_dir))
        if "clean_name" not in tags:
            set_variant(representation, output_name)
        if temp_data.without_handles and representation.contains_trait(
                Slate):
            # output starts with the content
            representation.remove_trait(Slate)
        set_files(
            representation,
            [
                Path(output_files.staging_dir) / filename
                for filename in output_files.files
            ],
            sequence=output_files.is_sequence,
            frame_rate=temp_data.fps,
        )
        if output_files.resolution:
            width, height = output_files.resolution
            representation.add_trait(PixelBased(
                display_window_width=width,
                display_window_height=height,
                pixel_aspect_ratio=1.0,
            ))
        source_width = source_height = None
        if output_files.source_resolution:
            source_width, source_height = output_files.source_resolution
        representation.add_trait(ReviewOutput(
            burnins=burnins,
            ffmpeg_cmd=subprcs_cmd,
            source_resolution_width=source_width,
            source_resolution_height=source_height,
            output_def=output_def,
        ))
        if frame_range is not None:
            _add_output_frame_traits(representation, frame_range, output_def)
        update_persistence(representation)

        self.log.debug(f"Rendered new representation: {representation}")
        return [representation]

    def _fill_sequence_gaps(
        self,
        instance: pyblish.api.Instance,
        source: Representation,
        source_dir: str,
        output_def: dict,
        temp_data: TraitTempData,
    ) -> dict[int, str]:
        """Fill missing frames of the source sequence.

        Returns:
            dict[int, str]: Created files by frame.

        """
        self.log.debug("Checking sequence to fill gaps in sequence..")
        files = temp_data.input_files
        collections = clique.assemble(files)[0]
        if len(collections) != 1:
            raise PublishError(
                f"Found multiple collections, expected one. {collections}"
            )
        collection = collections[0]

        fill_missing_frames = output_def["fill_missing_frames"]
        if fill_missing_frames == "closest_existing":
            return self.fill_sequence_gaps_from_existing(
                collection=collection,
                staging_dir=source_dir,
                start_frame=temp_data.frame_start,
                end_frame=temp_data.frame_end,
            )
        if fill_missing_frames == "blank":
            return self.fill_sequence_gaps_with_blanks(
                collection=collection,
                staging_dir=source_dir,
                start_frame=temp_data.frame_start,
                end_frame=temp_data.frame_end,
                resolution_width=temp_data.resolution_width,
                resolution_height=temp_data.resolution_height,
                extension=temp_data.input_ext,
                temp_data=temp_data,
            )
        if fill_missing_frames == "previous_version":
            _, new_frame_files = fill_sequence_gaps_with_previous_version(
                collection=collection,
                staging_dir=source_dir,
                instance=instance,
                current_repre_name=source.name,
                start_frame=temp_data.frame_start,
                end_frame=temp_data.frame_end,
            )
            if new_frame_files is not None:
                return new_frame_files
            self.log.warning(
                "Falling back to filling from currently last rendered."
            )
            return self.fill_sequence_gaps_from_existing(
                collection=collection,
                staging_dir=source_dir,
                start_frame=temp_data.frame_start,
                end_frame=temp_data.frame_end,
            )
        if fill_missing_frames == "only_rendered":
            temp_data.explicit_input_paths = [
                os.path.join(source_dir, file).replace("\\", "/")
                for file in files
            ]
            temp_data.frame_start = min(collection.indexes)
            temp_data.frame_end = max(collection.indexes)
        return {}

    def prepare_trait_temp_data(
        self,
        instance: pyblish.api.Instance,
        source: Representation,
        input_dir: str,
        output_def: dict,
        frame_range: Optional[FrameRangeData],
    ) -> TraitTempData:
        """Prepare values used across rendering of an output.

        Frame range, handles and frame rate are used from traits of the
        source representation. Instance data are used for representations
        without `FrameRanged` trait.

        Args:
            instance (pyblish.api.Instance): Publish instance.
            source (Representation): Source representation.
            input_dir (str): Directory with the input files.
            output_def (dict): Output definition.
            frame_range (Optional[FrameRangeData]): Frame range of
                the source.

        Returns:
            TraitTempData: Temp data.

        """
        fps = float(instance.data["fps"])
        slate_frames = 0
        if frame_range is not None:
            slate_frames = frame_range.slate_frames
            frame_start = frame_range.content_frame_start
            frame_end = frame_range.content_frame_end
            handle_start = frame_range.handle_start
            handle_end = frame_range.handle_end
            if frame_range.frame_rate is not None:
                fps = float(frame_range.frame_rate)
        else:
            frame_start = instance.data["frameStart"]
            frame_end = instance.data["frameEnd"]
            handle_start = instance.data.get("handleStart")
            handle_end = instance.data.get("handleEnd")
            if handle_start is None or handle_end is None:
                handle_start = instance.context.data["handleStart"]
                handle_end = instance.context.data["handleEnd"]

        frame_start_handle = frame_start - handle_start
        frame_end_handle = frame_end + handle_end

        without_handles = "no-handles" in output_def["tags"]
        if without_handles:
            output_frame_start = frame_start
            output_frame_end = frame_end
        else:
            # Slate frames at the start of the files are part of the output
            output_frame_start = frame_start_handle - slate_frames
            output_frame_end = frame_end_handle

        with_audio = not (
            "no-audio" in output_def["tags"]
            or not instance.data.get("audio")
        )

        input_files = [path.name for path in get_file_paths(source)]
        input_is_seq = is_sequence(source)
        input_ext = get_ext(source)
        input_allow_bg = False
        first_sequence_frame = None
        if input_is_seq:
            collections, _ = clique.assemble(input_files)
            input_frames = sorted(collections[0].indexes)
            first_sequence_frame = input_frames[0]
            if frame_range is not None:
                # Output without handles starts with the content - skip
                #   slate frames and handle frames (if they are in files)
                if without_handles:
                    first_sequence_frame += slate_frames
                    if frame_range.handles_in_files:
                        first_sequence_frame += handle_start
                    # `ReviewRenderer._ffmpeg_arguments` adds start handle
                    #   to the first frame of output without handles
                    if handle_start > 0 or handle_end > 0:
                        first_sequence_frame -= handle_start
            # Without frame range traits it is not known if the first
            #   frame is with or without handles
            elif (
                without_handles
                and len(input_frames) - handle_start
                >= output_frame_end - output_frame_start + 1
            ):
                first_sequence_frame += handle_start
            input_allow_bg = input_ext in self.alpha_exts

        temp_data = TraitTempData(
            fps=fps,
            frame_start=frame_start,
            frame_end=frame_end,
            handle_start=handle_start,
            handle_end=handle_end,
            frame_start_handle=frame_start_handle,
            frame_end_handle=frame_end_handle,
            output_frame_start=int(output_frame_start),
            output_frame_end=int(output_frame_end),
            pixel_aspect=instance.data.get("pixelAspect", 1),
            resolution_width=instance.data.get("resolutionWidth"),
            resolution_height=instance.data.get("resolutionHeight"),
            origin_repre=None,
            input_is_sequence=input_is_seq,
            first_sequence_frame=first_sequence_frame,
            input_allow_bg=input_allow_bg,
            with_audio=with_audio,
            without_handles=without_handles,
            handles_are_set=handle_start > 0 or handle_end > 0,
            input_ext=input_ext,
            explicit_input_paths=[],
            paths_to_remove=[],
        )
        temp_data.input_dir = input_dir
        temp_data.input_files = input_files
        return temp_data

    def input_output_paths(
        self,
        output_files: _OutputFiles,
        output_def: dict,
        temp_data: TraitTempData,
    ) -> None:
        """Resolve input and output file paths.

        Input is the source sequence, video or image. Output file names
        are created from the input file names and filename suffix of
        the output definition. Output directory is created.
        """
        input_dir = temp_data.input_dir
        input_files = temp_data.input_files
        if temp_data.input_is_sequence:
            collection = clique.assemble(input_files)[0][0]
            full_input_path = os.path.join(
                input_dir, collection.format("{head}{padding}{tail}")
            )
            filename = collection.format("{head}")
            if filename.endswith("."):
                filename = filename[:-1]
        else:
            full_input_path = os.path.join(input_dir, input_files[0])
            filename = os.path.splitext(input_files[0])[0]
        full_input_path_single_file = os.path.join(
            input_dir, input_files[0]
        )

        filled_files = temp_data.filled_files
        if filled_files:
            first_frame, first_file = next(iter(filled_files.items()))
            if first_file < full_input_path_single_file:
                self.log.warning(f"Using filled frame: '{first_file}'")
                full_input_path_single_file = first_file
                temp_data.first_sequence_frame = first_frame

        filename_suffix = output_def["filename_suffix"]
        output_ext = output_def.get("ext")
        if output_ext is None:
            output_ext = os.path.splitext(full_input_path)[1]
        output_ext = output_ext.lstrip(".").lower()
        self.log.debug(f"New representation ext: `{output_ext}`")

        output_ext_is_image = output_ext in self.image_exts
        output_is_sequence = (
            output_ext_is_image and "sequence" in output_def["tags"]
        )
        dst_staging_dir = output_files.staging_dir
        if output_is_sequence:
            filename_base = f"{filename}_{filename_suffix}"
            repr_file = "{}.%{:0>2}d.{}".format(
                filename_base,
                len(str(temp_data.output_frame_end)),
                output_ext,
            )
            files = [
                repr_file % frame
                for frame in range(
                    temp_data.output_frame_start,
                    temp_data.output_frame_end + 1,
                )
            ]
            full_output_path = os.path.join(
                dst_staging_dir, filename_base, repr_file
            )
        else:
            repr_file = f"{filename}_{filename_suffix}.{output_ext}"
            full_output_path = os.path.join(dst_staging_dir, repr_file)
            files = [repr_file]

        dst_staging_dir = os.path.normpath(os.path.dirname(full_output_path))
        if not os.path.exists(dst_staging_dir):
            self.log.debug(f"Creating dir: {dst_staging_dir}")
            os.makedirs(dst_staging_dir)

        output_files.ext = output_ext
        output_files.files = files
        output_files.is_sequence = output_is_sequence
        output_files.staging_dir = dst_staging_dir

        temp_data.full_input_path = full_input_path
        temp_data.full_input_path_single_file = full_input_path_single_file
        temp_data.full_output_path = full_output_path
        temp_data.output_ext_is_image = output_ext_is_image
        temp_data.output_is_sequence = output_is_sequence

        self.log.debug(f"Input path {full_input_path}")
        self.log.debug(f"Output path {full_output_path}")

    def rescaling_filters(
        self,
        temp_data: TraitTempData,
        output_def: dict,
        output_files: _OutputFiles,
    ) -> list[str]:
        """Prepare rescaling video filters and resolution of the output."""
        # `ReviewRenderer` reads tags and stores resolutions in the dict
        resolution_data: dict[str, Any] = {"tags": output_files.tags}
        filters = super().rescaling_filters(
            temp_data, output_def, resolution_data
        )
        output_files.resolution = (
            resolution_data["resolutionWidth"],
            resolution_data["resolutionHeight"],
        )
        output_files.source_resolution = (
            resolution_data["source_resolution_width"],
            resolution_data["source_resolution_height"],
        )
        return filters

    def lut_filters(
        self,
        output_files: _OutputFiles,
        instance: pyblish.api.Instance,
        input_args: list[str],
    ) -> list[str]:
        """Add lut file to output ffmpeg filters ("bake-lut" tag)."""
        return super().lut_filters(
            {"tags": output_files.tags}, instance, input_args
        )


class ExtractReviewTraits(pyblish.api.InstancePlugin):
    """Extracting Reviewable medias from trait-based representations.

    Runs the same ffmpeg pipeline as `ExtractReview` on
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
        representations = get_trait_representations(instance)
        self.log.debug(
            "Trait representations: {}".format(
                [representation.name for representation in representations]
            )
        )
        for representation in representations:
            should_process, skip_reason = review_repre_tag_filter(
                get_tags(representation)
            )
            if not should_process:
                self.log.debug(
                    f"Repre: {representation.name} - {skip_reason}. "
                    "Skipping"
                )
                continue

            try:
                ext = get_ext(representation)
            except PublishError:
                self.log.warning(
                    f"Representation \"{representation.name}\" has empty"
                    " files. Skipped."
                )
                continue
            if ext not in self.supported_exts:
                self.log.info(
                    f"Representation has unsupported extension \"{ext}\""
                )
                continue

            custom_tags: list[str] = []
            if representation.contains_trait(CustomTags):
                custom_tags = representation.get_trait(CustomTags).tags
            outputs = filter_outputs_by_custom_tags(
                profile_outputs, custom_tags, self.log
            )
            if not outputs:
                self.log.info(
                    "Skipped representation. All output definitions from"
                    " selected profile does not match to representation's"
                    f" custom tags. \"{custom_tags}\""
                )
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
        renderer = TraitReviewRenderer(
            self.log,
            image_exts=self.image_exts,
            video_exts=self.video_exts,
            alpha_exts=self.alpha_exts,
        )

        new_trait_representations: list[Representation] = []
        for source_repre, output_defs in outputs_per_repres:
            for new_representation in renderer.render_representation(
                instance, source_repre, output_defs, review_layers
            ):
                # same as legacy - rendered files are intermediate,
                # integration copies them
                add_trait_representation_files_for_cleanup(
                    instance, new_representation
                )
                new_trait_representations.append(new_representation)

        if new_trait_representations:
            self.log.debug(
                "Adding new trait representations: {}".format(
                    [r.name for r in new_trait_representations]
                )
            )
            add_trait_representations(instance, new_trait_representations)
