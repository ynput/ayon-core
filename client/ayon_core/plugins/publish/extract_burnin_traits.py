"""Trait-based burnin extractor.

Sibling to `extract_burnin.py` working on trait representations.
`ExtractBurnin` only looks at `instance.data["representations"]`, this
plugin only looks at `get_trait_representations(instance)`.

Burnin outputs are copies of their source representations pointing to
the new files and they replace the sources, same as in `ExtractBurnin`.
Frame range, frame rate and source resolution are read from traits of
the source - review outputs pass linked burnins, ffmpeg command and source
resolution in the `ReviewOutput` trait.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from typing import Any, Optional

import clique
import pyblish.api

from ayon_core.lib import (
    convert_input_paths_for_ffmpeg,
    run_ayon_launcher_process,
    should_convert_for_ffmpeg,
)
from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish import (
    add_trait_representation_files_for_cleanup,
    get_trait_representations,
    has_trait_representations,
    set_trait_representations,
)
from ayon_core.pipeline.publish.lib import (
    apply_plugin_settings_automatically,
    get_default_reviewable_layers,
)
from ayon_core.pipeline.publish.trait_utils import (
    copy_representation,
    get_file_paths,
    get_frame_rate,
    get_tags,
    get_variant,
    has_files,
    is_sequence,
    set_files,
    set_staging_directory,
    set_tags,
    set_variant,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    Representation,
    ReviewOutput,
    get_frame_range_data,
)
from ayon_core.plugins.publish import extract_burnin


class ExtractBurninTraits(extract_burnin.ExtractBurnin):
    """Create burnins for trait-based review representations."""

    label = "Extract burnins (Traits)"

    @classmethod
    def apply_settings(cls, project_settings):
        # Use `ExtractBurnin` settings, both plugins must create the same
        #   burnins for the same instance.
        apply_plugin_settings_automatically(
            cls,
            project_settings["core"]["publish"]["ExtractBurnin"],
        )

    def process(self, instance: pyblish.api.Instance) -> None:
        if not has_trait_representations(instance):
            return

        if not self.profiles:
            self.log.warning("No profiles present for create burnin")
            return

        representations = list(get_trait_representations(instance))
        self.process_representations(instance, representations)

        # Remove only representation tagged with both
        #   tags `delete` and `burnin`
        result = []
        for representation in representations:
            tags = get_tags(representation)
            if "delete" in tags and "burnin" in tags:
                self.log.debug(
                    f"Removing representation: {representation.name}"
                )
                continue
            result.append(representation)
        set_trait_representations(instance, result)

    def process_representations(
            self,
            instance: pyblish.api.Instance,
            representations: list[Representation]) -> None:
        """Create burnin outputs for representations.

        Args:
            instance (pyblish.api.Instance): Processed instance.
            representations (list[Representation]): Representations of
                the instance. Burnin outputs are added to the list and
                their sources are removed from it.

        """
        profile = self._get_profile(instance)
        if not profile:
            return

        # Pre-filter burnin definitions by instance families
        burnin_defs = self.filter_burnins_defs(profile, instance)
        if not burnin_defs:
            self.log.debug(
                "Skipped instance. Burnin definitions are not set for"
                f" profile \"{profile}\""
            )
            return

        burnins_per_repres = self._get_burnins_per_trait_representations(
            representations, burnin_defs
        )
        if not burnins_per_repres:
            self.log.debug(
                "Skipped instance. No representations found matching a burnin"
                " definition in: %s", burnin_defs
            )
            return

        burnin_options = self._get_burnin_options()
        basic_burnin_data, basic_temp_data = self.prepare_basic_data(
            instance
        )
        project_settings = instance.context.data["project_settings"]
        review_layers = get_default_reviewable_layers(project_settings)

        for source, source_burnin_defs in burnins_per_repres:
            burnin_data = copy.deepcopy(basic_burnin_data)
            temp_data = copy.deepcopy(basic_temp_data)
            self.prepare_trait_data(instance, source, burnin_data, temp_data)

            source_paths = get_file_paths(source)
            first_input_path = str(source_paths[0])
            do_convert = should_convert_for_ffmpeg(
                first_input_path, review_layers=review_layers
            )
            # If result is None the requirement of conversion can't be
            #   determined
            if do_convert is None:
                self.log.debug(
                    "Can't determine if representation requires conversion."
                    " Skipped."
                )
                continue

            input_dir = str(source_paths[0].parent)
            if do_convert:
                input_dir = get_temp_dir(
                    project_name=instance.context.data["projectName"],
                    use_local_temp=True,
                )
                convert_input_paths_for_ffmpeg(
                    [str(path) for path in source_paths],
                    input_dir,
                    review_layers=review_layers,
                    log=self.log,
                )

            self._fill_instance_burnin_data(instance, burnin_data)

            source_burnin_options = copy.deepcopy(burnin_options)
            # Use fps of representation for output in options
            fps = get_frame_rate(source)
            if fps is not None:
                source_burnin_options["fps"] = fps

            files_to_delete = []
            for idx, burnin_def in enumerate(source_burnin_defs):
                new_representation, input_paths = self._create_output(
                    source,
                    burnin_def,
                    input_dir,
                    burnin_data,
                    source_burnin_options,
                    first_output=idx == 0,
                    multiple_outputs=len(source_burnin_defs) > 1,
                )
                for filepath in input_paths:
                    if filepath not in files_to_delete:
                        files_to_delete.append(filepath)

                representations.append(new_representation)
                add_trait_representation_files_for_cleanup(
                    instance, new_representation
                )

            # Cleanup temp staging dir after processing of burnin definitions
            if do_convert:
                shutil.rmtree(input_dir)

            # Remove source representation
            representations.remove(source)

            self.log.debug(f"Files to delete: {files_to_delete}")
            for filepath in files_to_delete:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    self.log.debug(f"Removed: \"{filepath}\"")

    def _get_profile(
            self, instance: pyblish.api.Instance) -> Optional[dict[str, Any]]:
        """Get burnin profile matching the instance."""
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
        profile = filter_profiles(
            self.profiles,
            filtering_criteria,
            logger=self.log
        )
        if not profile:
            self.log.debug(
                "Skipped instance. None of profiles in presets are for"
                f" Host name: \"{host_name}\""
                f" | Product base type: \"{product_base_type}\""
                f" | Product name \"{product_name}\""
                f" | Task name \"{task_name}\""
                f" | Task type \"{task_type}\""
            )
        return profile

    def _get_burnins_per_trait_representations(
            self,
            representations: list[Representation],
            src_burnin_defs: list[dict]) -> list[tuple[Representation, list]]:
        """Get burnin definitions for each representation.

        Representation must be tagged "burnin". Burnin definitions linked
        to the representation (`ReviewOutput.burnins`) are used if any
        of them match, then definitions are filtered by tags.

        Args:
            representations (list[Representation]): Representations.
            src_burnin_defs (list[dict]): Burnin definitions.

        Returns:
            list[tuple[Representation, list]]: Representations with their
                burnin definitions.

        """
        filtered = []
        for representation in representations:
            tags = get_tags(representation)
            if "burnin" not in tags:
                self.log.debug(
                    f"Representation \"{representation.name}\" does not have"
                    " \"burnin\" tag. Skipped."
                )
                continue

            if not has_files(representation):
                self.log.warning(
                    f"Representation \"{representation.name}\" have empty"
                    " files. Skipped."
                )
                continue

            linked_burnins = []
            if representation.contains_trait(ReviewOutput):
                linked_burnins = representation.get_trait(
                    ReviewOutput).burnins
            burnin_defs = copy.deepcopy(src_burnin_defs)
            linked_burnin_defs = [
                burnin_def
                for burnin_def in burnin_defs
                if burnin_def["name"] in linked_burnins
            ]
            if linked_burnin_defs:
                burnin_defs = linked_burnin_defs

            burnin_defs = self.filter_burnins_by_tags(burnin_defs, tags)
            if not burnin_defs:
                self.log.debug(
                    "Skipped representation. All burnin definitions from"
                    " selected profile do not match to representation's"
                    f" tags. \"{tags}\""
                )
                continue
            filtered.append((representation, burnin_defs))
        return filtered

    def _fill_instance_burnin_data(
            self,
            instance: pyblish.api.Instance,
            burnin_data: dict[str, Any]) -> None:
        """Add anatomy, custom data and data members to burnin data."""
        anatomy = instance.context.data["anatomy"]
        filled_anatomy = anatomy.format_all(burnin_data)
        burnin_data["anatomy"] = filled_anatomy.get_solved()

        custom_data = copy.deepcopy(instance.data.get("customData") or {})
        # Backwards compatibility (since 2022/04/07)
        custom_data.update(instance.data.get("custom_burnin_data") or {})
        burnin_data["custom"] = custom_data

        burnin_data.update(instance.data.get("burninDataMembers", {}))

    def _create_output(
        self,
        source: Representation,
        burnin_def: dict[str, Any],
        input_dir: str,
        burnin_data: dict[str, Any],
        burnin_options: dict[str, Any],
        *,
        first_output: bool,
        multiple_outputs: bool,
    ) -> tuple[Representation, list[str]]:
        """Run burnin script for one burnin definition.

        Returns:
            tuple[Representation, list[str]]: Burnin output and paths to
                the input files.

        """
        filename_suffix = burnin_def["name"]
        source_paths = get_file_paths(source)
        output_dir = source_paths[0].parent

        new_representation = copy_representation(source)
        tags = [tag for tag in get_tags(source) if tag != "delete"]
        # Keep "ftrackreview" tag only on first output
        if not first_output and "ftrackreview" in tags:
            tags.remove("ftrackreview")
        set_tags(new_representation, tags)
        update_persistence(new_representation)

        if multiple_outputs:
            # Join previous output name with filename suffix to be able
            #   to have multiple outputs
            new_name = "_".join(
                [get_variant(source) or source.name, filename_suffix]
            )
            new_representation.name = new_name
            set_variant(new_representation, new_name)

        input_filenames = [path.name for path in source_paths]
        sequence = is_sequence(source) and len(input_filenames) > 1
        first_frame = None
        collections = []
        if sequence:
            collections, _ = clique.assemble(input_filenames)
            sequence = bool(collections)

        if sequence:
            collection = collections[0]
            indexes = sorted(collection.indexes)
            frame_pattern = "%0{}d".format(len(str(max(indexes))))
            head = collection.format("{head}")
            tail = collection.format("{tail}")
            input_filename = f"{head}{frame_pattern}{tail}"
            output_filename = f"{head}{frame_pattern}{filename_suffix}{tail}"
            output_filenames = [output_filename % idx for idx in indexes]
            first_frame = indexes[0]
            input_paths = [
                os.path.join(input_dir, filename).replace("\\", "/")
                for filename in input_filenames
            ]
        else:
            input_filename = input_filenames[0]
            basename, ext = os.path.splitext(input_filename)
            output_filename = basename + filename_suffix + ext
            output_filenames = [output_filename]
            input_paths = [
                os.path.join(input_dir, input_filename).replace("\\", "/")
            ]

        full_input_path = os.path.join(
            os.path.normpath(input_dir), input_filename
        ).replace("\\", "/")
        full_output_path = os.path.join(
            os.path.normpath(output_dir), output_filename
        ).replace("\\", "/")
        self.log.debug(f"full_input_path: {full_input_path}")
        self.log.debug(f"full_output_path: {full_output_path}")

        burnin_values = {
            key: burnin_def[key]
            for key in self.positions
            if burnin_def.get(key)
        }
        ffmpeg_cmd = ""
        if source.contains_trait(ReviewOutput):
            ffmpeg_cmd = source.get_trait(ReviewOutput).ffmpeg_cmd or ""

        script_data = {
            "input": full_input_path,
            "output": full_output_path,
            "burnin_data": burnin_data,
            "options": burnin_options,
            "values": burnin_values,
            "full_input_path": input_paths[0],
            "first_frame": first_frame,
            "ffmpeg_cmd": ffmpeg_cmd,
        }
        self.log.debug(
            f"script_data: {json.dumps(script_data, indent=4)}"
        )
        self._run_burnin_script(script_data)

        set_files(
            new_representation,
            [output_dir / filename for filename in output_filenames],
            sequence=is_sequence(source),
        )
        set_staging_directory(new_representation, output_dir)
        return new_representation, input_paths

    def _run_burnin_script(self, script_data: dict[str, Any]) -> None:
        """Run burnin script in AYON launcher process."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as temporary_json_file:
            json.dump(script_data, temporary_json_file)
        temporary_json_filepath = temporary_json_file.name.replace("\\", "/")

        args = [
            "run",
            self.burnin_script_path(),
            temporary_json_filepath,
            "--headless",
        ]
        self.log.debug("Executing: {}".format(" ".join(args)))
        try:
            run_ayon_launcher_process(*args, logger=self.log)
        finally:
            os.remove(temporary_json_filepath)

    def prepare_trait_data(
        self,
        instance: pyblish.api.Instance,
        representation: Representation,
        burnin_data: dict[str, Any],
        temp_data: dict[str, Any],
    ) -> None:
        """Prepare burnin data of the representation.

        Frame range and handles are used from traits of the representation.
        Frame range and handles from instance data are used for
        representations without frame range traits.

        Args:
            instance (pyblish.api.Instance): Currently processed Instance.
            representation (Representation): Processed representation.
            burnin_data (dict): Copy of basic burnin data based on instance
                data.
            temp_data (dict): Copy of basic temp data.

        """
        frame_range = get_frame_range_data(representation)
        if frame_range is not None:
            frame_start = frame_range.content_frame_start
            frame_end = frame_range.content_frame_end
            temp_data.update({
                "frame_start": frame_start,
                "frame_end": frame_end,
                "frame_start_handle": frame_start - frame_range.handle_start,
                "frame_end_handle": frame_end + frame_range.handle_end,
            })

        burnin_data["representation"] = representation.name

        tags = get_tags(representation)
        # no handles switch from profile tags
        if "no-handles" in tags:
            burnin_frame_start = temp_data["frame_start"]
            burnin_frame_end = temp_data["frame_end"]
        else:
            burnin_frame_start = temp_data["frame_start_handle"]
            burnin_frame_end = temp_data["frame_end_handle"]

        burnin_duration = burnin_frame_end - burnin_frame_start + 1
        burnin_data.update({
            "frame_start": burnin_frame_start,
            "frame_end": burnin_frame_end,
            "duration": burnin_duration,
        })
        temp_data["duration"] = burnin_duration

        # Move frame start by 1 frame when slate is used.
        burnin_slate_frame_start = burnin_frame_start
        if (
            "slate" in instance.data["families"]
            and "slate-frame" in tags
        ):
            burnin_slate_frame_start -= 1
        self.log.debug(
            f"burnin_slate_frame_start: {burnin_slate_frame_start}"
        )
        burnin_data.update({
            "slate_frame_start": burnin_slate_frame_start,
            "slate_frame_end": burnin_frame_end,
            "slate_duration": (
                burnin_frame_end - burnin_slate_frame_start + 1
            )
        })

        # burnin source resolution which might be different than on review
        if representation.contains_trait(ReviewOutput):
            review_output = representation.get_trait(ReviewOutput)
            width = review_output.source_resolution_width
            height = review_output.source_resolution_height
            if width and height:
                burnin_data.update({
                    "source_resolution_width": width,
                    "source_resolution_height": height,
                })
