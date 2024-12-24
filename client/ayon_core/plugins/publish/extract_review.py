import os
import re
import copy
import json
import shutil
import subprocess
from abc import ABC, abstractmethod

import clique
import speedcopy
import pyblish.api

from ayon_core.lib import (
    get_ffmpeg_tool_args,
    filter_profiles,
    path_to_subprocess_arg,
    run_subprocess,
)
from ayon_core.lib.transcoding import (
    IMAGE_EXTENSIONS,
    get_ffprobe_streams,
    should_convert_for_ffmpeg,
    get_review_layer_name,
    convert_input_paths_for_ffmpeg,
)
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish import (
    KnownPublishError,
    get_publish_instance_label,
)
from ayon_core.pipeline.publish.lib import add_repre_files_for_cleanup


def frame_to_timecode(frame: int, fps: float) -> str:
    """Convert a frame number and FPS to editorial timecode (HH:MM:SS:FF).

    Unlike `ayon_core.pipeline.editorial.frames_to_timecode` this does not
    rely on the `opentimelineio` package, so it can be used across hosts that
    do not have it available.

    Args:
        frame (int): The frame number to be converted.
        fps (float): The frames per second of the video.

    Returns:
        str: The timecode in HH:MM:SS:FF format.
    """
    # Calculate total seconds
    total_seconds = frame / fps

    # Extract hours, minutes, and seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    # Adjust for non-integer FPS by rounding the remaining frames appropriately
    remaining_frames = round((total_seconds - int(total_seconds)) * fps)

    # Format and return the timecode
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{remaining_frames:02d}"


class ExtractReview(pyblish.api.InstancePlugin):
    """Extracting Review mov file for Ftrack

    Compulsory attribute of representation is tags list with "review",
    otherwise the representation is ignored.

    All new representations are created and encoded by ffmpeg following
    presets found in AYON Settings interface at
    `project_settings/global/publish/ExtractReview/profiles:outputs`.
    """

    label = "Extract Review"
    order = pyblish.api.ExtractorOrder + 0.02
    families = ["review"]
    hosts = [
        "nuke",
        "maya",
        "blender",
        "houdini",
        "max",
        "shell",
        "hiero",
        "premiere",
        "harmony",
        "traypublisher",
        "fusion",
        "tvpaint",
        "resolve",
        "webpublisher",
        "aftereffects",
        "flame",
        "unreal"
    ]

    # Supported extensions
    image_exts = ["exr", "jpg", "jpeg", "png", "dpx", "tga", "tiff", "tif"]
    video_exts = ["mov", "mp4"]
    supported_exts = image_exts + video_exts

    alpha_exts = ["exr", "png", "dpx"]

    # Preset attributes
    profiles = []

    def process(self, instance):
        self.log.debug(str(instance.data["representations"]))
        # Skip review when requested.
        if not instance.data.get("review", True):
            return

        # Run processing
        self.main_process(instance)

        # Make sure cleanup happens and pop representations with "delete" tag.
        for repre in tuple(instance.data["representations"]):
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

    def _get_outputs_for_instance(self, instance):
        host_name = instance.context.data["hostName"]
        product_type = instance.data["productType"]

        self.log.debug("Host: \"{}\"".format(host_name))
        self.log.debug("Product type: \"{}\"".format(product_type))

        profile = filter_profiles(
            self.profiles,
            {
                "hosts": host_name,
                "product_types": product_type,
            },
            logger=self.log)
        if not profile:
            self.log.info((
                "Skipped instance. None of profiles in presets are for"
                " Host: \"{}\" | Product type: \"{}\""
            ).format(host_name, product_type))
            return

        self.log.debug("Matching profile: \"{}\"".format(json.dumps(profile)))

        product_name = instance.data.get("productName")
        instance_families = self.families_from_instance(instance)
        filtered_outputs = self.filter_output_defs(
            profile, product_name, instance_families
        )
        if not filtered_outputs:
            self.log.info((
                "Skipped instance. All output definitions from selected"
                " profile do not match instance families \"{}\" or"
                " product name \"{}\"."
            ).format(str(instance_families), product_name))

        # Store `filename_suffix` to save arguments
        profile_outputs = []
        for filename_suffix, definition in filtered_outputs.items():
            definition["filename_suffix"] = filename_suffix
            profile_outputs.append(definition)

        return profile_outputs

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

            input_ext = repre["ext"]
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
            outputs = self.filter_outputs_by_custom_tags(
                profile_outputs, custom_tags)
            if not outputs:
                self.log.info((
                    "Skipped representation. All output definitions from"
                    " selected profile does not match to representation's"
                    " custom tags. \"{}\""
                ).format(str(custom_tags)))
                continue

            outputs_per_representations.append((repre, outputs))
        return outputs_per_representations

    def _single_frame_filter(self, input_filepaths, output_defs):
        single_frame_image = False
        if len(input_filepaths) == 1:
            ext = os.path.splitext(input_filepaths[0])[-1]
            single_frame_image = ext.lower() in IMAGE_EXTENSIONS

        filtered_defs = []
        for output_def in output_defs:
            output_filters = output_def.get("filter") or {}
            frame_filter = output_filters.get("single_frame_filter")
            if (
                (not single_frame_image and frame_filter == "single_frame")
                or (single_frame_image and frame_filter == "multi_frame")
            ):
                continue

            filtered_defs.append(output_def)

        return filtered_defs

    def main_process(self, instance):
        instance_label = get_publish_instance_label(instance)
        self.log.debug("Processing instance \"{}\"".format(instance_label))
        profile_outputs = self._get_outputs_for_instance(instance)
        if not profile_outputs:
            return

        # Loop through representations
        outputs_per_repres = self._get_outputs_per_representations(
            instance, profile_outputs
        )

        for repre, output_defs in outputs_per_repres:
            # Check if input should be preconverted before processing
            # Store original staging dir (it's value may change)
            src_repre_staging_dir = repre["stagingDir"]
            # Receive filepath to first file in representation
            first_input_path = None
            input_filepaths = []
            if not self.input_is_sequence(repre):
                first_input_path = os.path.join(
                    src_repre_staging_dir, repre["files"]
                )
                input_filepaths.append(first_input_path)
            else:
                for filename in repre["files"]:
                    filepath = os.path.join(
                        src_repre_staging_dir, filename
                    )
                    input_filepaths.append(filepath)
                    if first_input_path is None:
                        first_input_path = filepath

            filtered_output_defs = self._single_frame_filter(
                input_filepaths, output_defs
            )
            if not filtered_output_defs:
                self.log.debug((
                    "Repre: {} - All output definitions were filtered"
                    " out by single frame filter. Skipping"
                ).format(repre["name"]))
                continue

            # Skip if file is not set
            if first_input_path is None:
                self.log.warning((
                    "Representation \"{}\" have empty files. Skipped."
                ).format(repre["name"]))
                continue

            # Determine if representation requires pre conversion for ffmpeg
            do_convert = should_convert_for_ffmpeg(first_input_path)
            # If result is None the requirement of conversion can't be
            #   determined
            if do_convert is None:
                self.log.info((
                    "Can't determine if representation requires conversion."
                    " Skipped."
                ))
                continue

            layer_name = get_review_layer_name(first_input_path)

            # Do conversion if needed
            #   - change staging dir of source representation
            #   - must be set back after output definitions processing
            if do_convert:
                new_staging_dir = get_temp_dir(
                    project_name=instance.context.data["projectName"],
                    use_local_temp=True,
                )
                repre["stagingDir"] = new_staging_dir

                convert_input_paths_for_ffmpeg(
                    input_filepaths,
                    new_staging_dir,
                    self.log
                )

            try:
                self._render_output_definitions(
                    instance,
                    repre,
                    src_repre_staging_dir,
                    filtered_output_defs,
                    layer_name
                )

            finally:
                # Make sure temporary staging is cleaned up and representation
                #   has set origin stagingDir
                if do_convert:
                    # Set staging dir of source representation back to previous
                    #   value
                    repre["stagingDir"] = src_repre_staging_dir
                    if os.path.exists(new_staging_dir):
                        shutil.rmtree(new_staging_dir)

    def _render_output_definitions(
        self,
        instance,
        repre,
        src_repre_staging_dir,
        output_definitions,
        layer_name
    ):
        fill_data = copy.deepcopy(instance.data["anatomyData"])
        for _output_def in output_definitions:
            output_def = copy.deepcopy(_output_def)
            # Make sure output definition has "tags" key
            if "tags" not in output_def:
                output_def["tags"] = []

            if "burnins" not in output_def:
                output_def["burnins"] = []

            # Create copy of representation
            new_repre = copy.deepcopy(repre)
            new_tags = new_repre.get("tags") or []
            # Make sure new representation has origin staging dir
            #   - this is because source representation may change
            #       it's staging dir because of ffmpeg conversion
            new_repre["stagingDir"] = src_repre_staging_dir

            # Remove "delete" tag from new repre if there is
            if "delete" in new_tags:
                new_tags.remove("delete")

            if "need_thumbnail" in new_tags:
                new_tags.remove("need_thumbnail")

            # Add additional tags from output definition to representation
            for tag in output_def["tags"]:
                if tag not in new_tags:
                    new_tags.append(tag)

            # Return tags to new representation
            new_repre["tags"] = new_tags

            # Add burnin link from output definition to representation
            for burnin in output_def["burnins"]:
                if burnin not in new_repre.get("burnins", []):
                    if not new_repre.get("burnins"):
                        new_repre["burnins"] = []
                    new_repre["burnins"].append(str(burnin))

            self.log.debug(
                "Linked burnins: `{}`".format(new_repre.get("burnins"))
            )

            self.log.debug(
                "New representation tags: `{}`".format(
                    new_repre.get("tags"))
            )

            temp_data = self.prepare_temp_data(instance, repre, output_def)
            files_to_clean = []
            if temp_data["input_is_sequence"]:
                self.log.debug("Checking sequence to fill gaps in sequence..")
                files_to_clean = self.fill_sequence_gaps(
                    files=temp_data["origin_repre"]["files"],
                    staging_dir=new_repre["stagingDir"],
                    start_frame=temp_data["frame_start"],
                    end_frame=temp_data["frame_end"]
                )

            # create or update outputName
            output_name = new_repre.get("outputName", "")
            output_ext = new_repre["ext"]
            if output_name:
                output_name += "_"
            output_name += output_def["filename_suffix"]
            if temp_data["without_handles"]:
                output_name += "_noHandles"

            # add outputName to anatomy format fill_data
            fill_data.update({
                "output": output_name,
                "ext": output_ext,

                # By adding `timecode` as data we can use it
                # in the ffmpeg arguments for `--timecode` so that editorial
                # like Resolve or Premiere can detect the start frame for e.g.
                # review output files
                "timecode": frame_to_timecode(
                    frame=temp_data["frame_start_handle"],
                    fps=float(instance.data["fps"])
                )
            })

            try:  # temporary until oiiotool is supported cross platform
                ffmpeg_args = self._ffmpeg_arguments(
                    output_def,
                    instance,
                    new_repre,
                    temp_data,
                    fill_data,
                    layer_name,
                )
            except ZeroDivisionError:
                # TODO recalculate width and height using OIIO before
                #   conversion
                if 'exr' in temp_data["origin_repre"]["ext"]:
                    self.log.warning(
                        (
                            "Unsupported compression on input files."
                            " Skipping!!!"
                        ),
                        exc_info=True
                    )
                    return
                raise NotImplementedError

            subprcs_cmd = " ".join(ffmpeg_args)

            # run subprocess
            self.log.debug("Executing: {}".format(subprcs_cmd))

            run_subprocess(subprcs_cmd, shell=True, logger=self.log)

            # delete files added to fill gaps
            if files_to_clean:
                for f in files_to_clean:
                    os.unlink(f)

            new_repre.update({
                "fps": temp_data["fps"],
                "name": "{}_{}".format(output_name, output_ext),
                "outputName": output_name,
                "outputDef": output_def,
                "frameStartFtrack": temp_data["output_frame_start"],
                "frameEndFtrack": temp_data["output_frame_end"],
                "ffmpeg_cmd": subprcs_cmd
            })

            # Force to pop these key if are in new repre
            new_repre.pop("thumbnail", None)
            if "clean_name" in new_repre.get("tags", []):
                new_repre.pop("outputName")

            # adding representation
            self.log.debug(
                "Adding new representation: {}".format(new_repre)
            )
            instance.data["representations"].append(new_repre)

            add_repre_files_for_cleanup(instance, new_repre)

    def input_is_sequence(self, repre):
        """Deduce from representation data if input is sequence."""
        # TODO GLOBAL ISSUE - Find better way how to find out if input
        #  is sequence. Issues (in theory):
        #   - there may be multiple files ant not be sequence
        #   - remainders are not checked at all
        #   - there can be more than one collection
        return isinstance(repre["files"], (list, tuple))

    def prepare_temp_data(self, instance, repre, output_def):
        """Prepare dictionary with values used across extractor's process.

        All data are collected from instance, context, origin representation
        and output definition.

        There are few required keys in Instance data: "frameStart", "frameEnd"
        and "fps".

        Args:
            instance (Instance): Currently processed instance.
            repre (dict): Representation from which new representation was
                copied.
            output_def (dict): Definition of output of this plugin.

        Returns:
            dict: All data which are used across methods during process.
                Their values should not change during process but new keys
                with values may be added.
        """

        frame_start = instance.data["frameStart"]
        frame_end = instance.data["frameEnd"]

        # Try to get handles from instance
        handle_start = instance.data.get("handleStart")
        handle_end = instance.data.get("handleEnd")
        # If even one of handle values is not set on instance use
        # handles from context
        if handle_start is None or handle_end is None:
            handle_start = instance.context.data["handleStart"]
            handle_end = instance.context.data["handleEnd"]

        frame_start_handle = frame_start - handle_start
        frame_end_handle = frame_end + handle_end

        # Change output frames when output should be without handles
        without_handles = bool("no-handles" in output_def["tags"])
        if without_handles:
            output_frame_start = frame_start
            output_frame_end = frame_end
        else:
            output_frame_start = frame_start_handle
            output_frame_end = frame_end_handle

        handles_are_set = handle_start > 0 or handle_end > 0

        with_audio = True
        if (
            # Check if has `no-audio` tag
            "no-audio" in output_def["tags"]
            # Check if instance has ny audio in data
            or not instance.data.get("audio")
        ):
            with_audio = False

        input_is_sequence = self.input_is_sequence(repre)
        input_allow_bg = False
        first_sequence_frame = None
        if input_is_sequence and repre["files"]:
            # Calculate first frame that should be used
            cols, _ = clique.assemble(repre["files"])
            input_frames = list(sorted(cols[0].indexes))
            first_sequence_frame = input_frames[0]
            # WARNING: This is an issue as we don't know if first frame
            #   is with or without handles!
            # - handle start is added but how do not know if we should
            output_duration = (output_frame_end - output_frame_start) + 1
            if (
                without_handles
                and len(input_frames) - handle_start >= output_duration
            ):
                first_sequence_frame += handle_start

            ext = os.path.splitext(repre["files"][0])[1].replace(".", "")
            if ext.lower() in self.alpha_exts:
                input_allow_bg = True

        return {
            "fps": float(instance.data["fps"]),
            "frame_start": frame_start,
            "frame_end": frame_end,
            "handle_start": handle_start,
            "handle_end": handle_end,
            "frame_start_handle": frame_start_handle,
            "frame_end_handle": frame_end_handle,
            "output_frame_start": int(output_frame_start),
            "output_frame_end": int(output_frame_end),
            "pixel_aspect": instance.data.get("pixelAspect", 1),
            "resolution_width": instance.data.get("resolutionWidth"),
            "resolution_height": instance.data.get("resolutionHeight"),
            "origin_repre": repre,
            "input_is_sequence": input_is_sequence,
            "first_sequence_frame": first_sequence_frame,
            "input_allow_bg": input_allow_bg,
            "with_audio": with_audio,
            "without_handles": without_handles,
            "handles_are_set": handles_are_set
        }

    def _ffmpeg_arguments(
        self,
        output_def,
        instance,
        new_repre,
        temp_data,
        fill_data,
        layer_name
    ):
        """Prepares ffmpeg arguments for expected extraction.

        Prepares input and output arguments based on output definition and
        input files.

        Args:
            output_def (dict): Currently processed output definition.
            instance (Instance): Currently processed instance.
            new_repre (dict): Representation representing output of this
                process.
            temp_data (dict): Base data for successful process.
        """

        # Get FFmpeg arguments from profile presets
        out_def_ffmpeg_args = output_def.get("ffmpeg_args") or {}

        _ffmpeg_input_args = out_def_ffmpeg_args.get("input") or []
        _ffmpeg_output_args = out_def_ffmpeg_args.get("output") or []
        _ffmpeg_video_filters = out_def_ffmpeg_args.get("video_filters") or []
        _ffmpeg_audio_filters = out_def_ffmpeg_args.get("audio_filters") or []

        # Cleanup empty strings
        ffmpeg_input_args = [
            value for value in _ffmpeg_input_args if value.strip()
        ]
        ffmpeg_video_filters = [
            value for value in _ffmpeg_video_filters if value.strip()
        ]
        ffmpeg_audio_filters = [
            value for value in _ffmpeg_audio_filters if value.strip()
        ]

        ffmpeg_output_args = []
        for value in _ffmpeg_output_args:
            value = value.strip()
            if not value:
                continue
            try:
                value = value.format(**fill_data)
            except Exception:
                self.log.warning(
                    "Failed to format ffmpeg argument: {}".format(value),
                    exc_info=True
                )
                pass
            ffmpeg_output_args.append(value)

        # Prepare input and output filepaths
        self.input_output_paths(new_repre, output_def, temp_data)

        # Set output frames len to 1 when output is single image
        if (
            temp_data["output_ext_is_image"]
            and not temp_data["output_is_sequence"]
        ):
            output_frames_len = 1

        else:
            output_frames_len = (
                temp_data["output_frame_end"]
                - temp_data["output_frame_start"]
                + 1
            )

        duration_seconds = float(output_frames_len / temp_data["fps"])

        # Define which layer should be used
        if layer_name:
            ffmpeg_input_args.extend(["-layer", layer_name])

        if temp_data["input_is_sequence"]:
            # Set start frame of input sequence (just frame in filename)
            # - definition of input filepath
            # - add handle start if output should be without handles
            start_number = temp_data["first_sequence_frame"]
            if temp_data["without_handles"] and temp_data["handles_are_set"]:
                start_number += temp_data["handle_start"]
            ffmpeg_input_args.extend([
                "-start_number", str(start_number)
            ])

            # TODO add fps mapping `{fps: fraction}` ?
            # - e.g.: {
            #     "25": "25/1",
            #     "24": "24/1",
            #     "23.976": "24000/1001"
            # }
            # Add framerate to input when input is sequence
            ffmpeg_input_args.extend([
                "-framerate", str(temp_data["fps"])
            ])
            # Add duration of an input sequence if output is video
            if not temp_data["output_is_sequence"]:
                ffmpeg_input_args.extend([
                    "-to", "{:0.10f}".format(duration_seconds)
                ])

        if temp_data["output_is_sequence"]:
            # Set start frame of output sequence (just frame in filename)
            # - this is definition of an output
            ffmpeg_output_args.extend([
                "-start_number", str(temp_data["output_frame_start"])
            ])

        # Change output's duration and start point if should not contain
        # handles
        if temp_data["without_handles"] and temp_data["handles_are_set"]:
            # Set output duration in seconds
            ffmpeg_output_args.extend([
                "-t", "{:0.10}".format(duration_seconds)
            ])

            # Add -ss (start offset in seconds) if input is not sequence
            if not temp_data["input_is_sequence"]:
                start_sec = float(temp_data["handle_start"]) / temp_data["fps"]
                # Set start time without handles
                # - Skip if start sec is 0.0
                if start_sec > 0.0:
                    ffmpeg_input_args.extend([
                        "-ss", "{:0.10f}".format(start_sec)
                    ])

        # Set frame range of output when input or output is sequence
        elif temp_data["output_is_sequence"]:
            ffmpeg_output_args.extend([
                "-frames:v", str(output_frames_len)
            ])

        # Add video/image input path
        ffmpeg_input_args.extend([
            "-i", path_to_subprocess_arg(temp_data["full_input_path"])
        ])

        # Add audio arguments if there are any. Skipped when output are images.
        if not temp_data["output_ext_is_image"] and temp_data["with_audio"]:
            audio_in_args, audio_filters, audio_out_args = self.audio_args(
                instance, temp_data, duration_seconds
            )
            ffmpeg_input_args.extend(audio_in_args)
            ffmpeg_audio_filters.extend(audio_filters)
            ffmpeg_output_args.extend(audio_out_args)

        res_filters = self.rescaling_filters(temp_data, output_def, new_repre)
        ffmpeg_video_filters.extend(res_filters)

        ffmpeg_input_args = self.split_ffmpeg_args(ffmpeg_input_args)

        lut_filters = self.lut_filters(new_repre, instance, ffmpeg_input_args)
        ffmpeg_video_filters.extend(lut_filters)

        bg_alpha = 0.0
        bg_color = output_def.get("bg_color")
        if bg_color:
            bg_red, bg_green, bg_blue, bg_alpha = bg_color

        if bg_alpha > 0.0:
            if not temp_data["input_allow_bg"]:
                self.log.info((
                    "Output definition has defined BG color input was"
                    " resolved as does not support adding BG."
                ))
            else:
                bg_color_hex = "#{0:0>2X}{1:0>2X}{2:0>2X}".format(
                    bg_red, bg_green, bg_blue
                )
                bg_color_str = "{}@{}".format(bg_color_hex, bg_alpha)

                self.log.info("Applying BG color {}".format(bg_color_str))
                color_args = [
                    "split=2[bg][fg]",
                    "[bg]drawbox=c={}:replace=1:t=fill[bg]".format(
                        bg_color_str
                    ),
                    "[bg][fg]overlay=format=auto"
                ]
                # Prepend bg color change before all video filters
                # NOTE at the time of creation it is required as video filters
                #   from settings may affect color of BG
                #   e.g. `eq` can remove alpha from input
                for arg in reversed(color_args):
                    ffmpeg_video_filters.insert(0, arg)

        # Add argument to override output file
        ffmpeg_output_args.append("-y")

        # NOTE This must be latest added item to output arguments.
        ffmpeg_output_args.append(
            path_to_subprocess_arg(temp_data["full_output_path"])
        )

        return self.ffmpeg_full_args(
            ffmpeg_input_args,
            ffmpeg_video_filters,
            ffmpeg_audio_filters,
            ffmpeg_output_args
        )

    def split_ffmpeg_args(self, in_args):
        """Makes sure all entered arguments are separated in individual items.

        Split each argument string with " -" to identify if string contains
        one or more arguments.
        """
        splitted_args = []
        for arg in in_args:
            sub_args = arg.split(" -")
            if len(sub_args) == 1:
                if arg and arg not in splitted_args:
                    splitted_args.append(arg)
                continue

            for idx, arg in enumerate(sub_args):
                if idx != 0:
                    arg = "-" + arg

                if arg and arg not in splitted_args:
                    splitted_args.append(arg)
        return splitted_args

    def ffmpeg_full_args(
        self, input_args, video_filters, audio_filters, output_args
    ):
        """Post processing of collected FFmpeg arguments.

        Just verify that output arguments does not contain video or audio
        filters which may cause issues because of duplicated argument entry.
        Filters found in output arguments are moved to list they belong to.

        Args:
            input_args (list): All collected ffmpeg arguments with inputs.
            video_filters (list): All collected video filters.
            audio_filters (list): All collected audio filters.
            output_args (list): All collected ffmpeg output arguments with
                output filepath.

        Returns:
            list: Containing all arguments ready to run in subprocess.
        """
        output_args = self.split_ffmpeg_args(output_args)

        video_args_dentifiers = ["-vf", "-filter:v"]
        audio_args_dentifiers = ["-af", "-filter:a"]
        for arg in tuple(output_args):
            for identifier in video_args_dentifiers:
                if arg.startswith("{} ".format(identifier)):
                    output_args.remove(arg)
                    arg = arg.replace(identifier, "").strip()
                    video_filters.append(arg)

            for identifier in audio_args_dentifiers:
                if arg.startswith("{} ".format(identifier)):
                    output_args.remove(arg)
                    arg = arg.replace(identifier, "").strip()
                    audio_filters.append(arg)

        all_args = [
            subprocess.list2cmdline(get_ffmpeg_tool_args("ffmpeg"))
        ]
        all_args.extend(input_args)
        if video_filters:
            all_args.append("-filter:v")
            all_args.append("\"{}\"".format(",".join(video_filters)))

        if audio_filters:
            all_args.append("-filter:a")
            all_args.append("\"{}\"".format(",".join(audio_filters)))

        all_args.extend(output_args)

        return all_args

    def fill_sequence_gaps(self, files, staging_dir, start_frame, end_frame):
        # type: (list, str, int, int) -> list
        """Fill missing files in sequence by duplicating existing ones.

        This will take nearest frame file and copy it with so as to fill
        gaps in sequence. Last existing file there is is used to for the
        hole ahead.

        Args:
            files (list): List of representation files.
            staging_dir (str): Path to staging directory.
            start_frame (int): Sequence start (no matter what files are there)
            end_frame (int): Sequence end (no matter what files are there)

        Returns:
            list of added files. Those should be cleaned after work
                is done.

        Raises:
            KnownPublishError: if more than one collection is obtained.
        """

        collections = clique.assemble(files)[0]
        if len(collections) != 1:
            raise KnownPublishError(
                "Multiple collections {} found.".format(collections))

        col = collections[0]

        # Prepare which hole is filled with what frame
        #   - the frame is filled only with already existing frames
        prev_frame = next(iter(col.indexes))
        hole_frame_to_nearest = {}
        for frame in range(int(start_frame), int(end_frame) + 1):
            if frame in col.indexes:
                prev_frame = frame
            else:
                # Use previous frame as source for hole
                hole_frame_to_nearest[frame] = prev_frame

        # Calculate paths
        added_files = []
        col_format = col.format("{head}{padding}{tail}")
        for hole_frame, src_frame in hole_frame_to_nearest.items():
            hole_fpath = os.path.join(staging_dir, col_format % hole_frame)
            src_fpath = os.path.join(staging_dir, col_format % src_frame)
            if not os.path.isfile(src_fpath):
                raise KnownPublishError(
                    "Missing previously detected file: {}".format(src_fpath))

            speedcopy.copyfile(src_fpath, hole_fpath)
            added_files.append(hole_fpath)

        return added_files

    def input_output_paths(self, new_repre, output_def, temp_data):
        """Deduce input nad output file paths based on entered data.

        Input may be sequence of images, video file or single image file and
        same can be said about output, this method helps to find out what
        their paths are.

        It is validated that output directory exist and creates if not.

        During process are set "files", "stagingDir", "ext" and
        "sequence_file" (if output is sequence) keys to new representation.
        """

        repre = temp_data["origin_repre"]
        src_staging_dir = repre["stagingDir"]
        dst_staging_dir = new_repre["stagingDir"]

        if temp_data["input_is_sequence"]:
            collections = clique.assemble(repre["files"])[0]
            full_input_path = os.path.join(
                src_staging_dir,
                collections[0].format("{head}{padding}{tail}")
            )

            filename = collections[0].format("{head}")
            if filename.endswith("."):
                filename = filename[:-1]

            # Make sure to have full path to one input file
            full_input_path_single_file = os.path.join(
                src_staging_dir, repre["files"][0]
            )

        else:
            full_input_path = os.path.join(
                src_staging_dir, repre["files"]
            )
            filename = os.path.splitext(repre["files"])[0]

            # Make sure to have full path to one input file
            full_input_path_single_file = full_input_path

        filename_suffix = output_def["filename_suffix"]

        output_ext = output_def.get("ext")
        # Use input extension if output definition do not specify it
        if output_ext is None:
            output_ext = os.path.splitext(full_input_path)[1]

        # TODO Define if extension should have dot or not
        if output_ext.startswith("."):
            output_ext = output_ext[1:]

        output_ext = output_ext.lower()

        # Store extension to representation
        new_repre["ext"] = output_ext

        self.log.debug("New representation ext: `{}`".format(output_ext))

        # Output is image file sequence with frames
        output_ext_is_image = bool(output_ext in self.image_exts)
        output_is_sequence = bool(
            output_ext_is_image
            and "sequence" in output_def["tags"]
        )
        if output_is_sequence:
            new_repre_files = []
            frame_start = temp_data["output_frame_start"]
            frame_end = temp_data["output_frame_end"]

            filename_base = "{}_{}".format(filename, filename_suffix)
            # Temporary template for frame filling. Example output:
            # "basename.%04d.exr" when `frame_end` == 1001
            repr_file = "{}.%{:0>2}d.{}".format(
                filename_base, len(str(frame_end)), output_ext
            )

            for frame in range(frame_start, frame_end + 1):
                new_repre_files.append(repr_file % frame)

            new_repre["sequence_file"] = repr_file
            full_output_path = os.path.join(
                dst_staging_dir, filename_base, repr_file
            )

        else:
            repr_file = "{}_{}.{}".format(
                filename, filename_suffix, output_ext
            )
            full_output_path = os.path.join(dst_staging_dir, repr_file)
            new_repre_files = repr_file

        # Store files to representation
        new_repre["files"] = new_repre_files

        # Make sure stagingDire exists
        dst_staging_dir = os.path.normpath(os.path.dirname(full_output_path))
        if not os.path.exists(dst_staging_dir):
            self.log.debug("Creating dir: {}".format(dst_staging_dir))
            os.makedirs(dst_staging_dir)

        # Store stagingDir to representation
        new_repre["stagingDir"] = dst_staging_dir

        # Store paths to temp data
        temp_data["full_input_path"] = full_input_path
        temp_data["full_input_path_single_file"] = full_input_path_single_file
        temp_data["full_output_path"] = full_output_path

        # Store information about output
        temp_data["output_ext_is_image"] = output_ext_is_image
        temp_data["output_is_sequence"] = output_is_sequence

        self.log.debug("Input path {}".format(full_input_path))
        self.log.debug("Output path {}".format(full_output_path))

    def audio_args(self, instance, temp_data, duration_seconds):
        """Prepares FFMpeg arguments for audio inputs."""
        audio_in_args = []
        audio_filters = []
        audio_out_args = []
        audio_inputs = instance.data.get("audio")
        if not audio_inputs:
            return audio_in_args, audio_filters, audio_out_args

        for audio in audio_inputs:
            # NOTE modified, always was expected "frameStartFtrack" which is
            # STRANGE?!!! There should be different key, right?
            # TODO use different frame start!
            offset_seconds = 0
            frame_start_ftrack = instance.data.get("frameStartFtrack")
            if frame_start_ftrack is not None:
                offset_frames = frame_start_ftrack - audio["offset"]
                offset_seconds = offset_frames / temp_data["fps"]

            if offset_seconds > 0:
                audio_in_args.append(
                    "-ss {}".format(offset_seconds)
                )

            elif offset_seconds < 0:
                audio_in_args.append(
                    "-itsoffset {}".format(abs(offset_seconds))
                )

            # Audio duration is offset from `-ss`
            audio_duration = duration_seconds + offset_seconds

            # Set audio duration
            audio_in_args.append("-to {:0.10f}".format(audio_duration))

            # Ignore video data from audio input
            audio_in_args.append("-vn")

            # Add audio input path
            audio_in_args.append("-i {}".format(
                path_to_subprocess_arg(audio["filename"])
            ))

        # NOTE: These were changed from input to output arguments.
        # NOTE: value in "-ac" was hardcoded to 2, changed to audio inputs len.
        # Need to merge audio if there are more than 1 input.
        if len(audio_inputs) > 1:
            audio_out_args.append("-filter_complex amerge")
            audio_out_args.append("-ac {}".format(len(audio_inputs)))

        return audio_in_args, audio_filters, audio_out_args

    def get_letterbox_filters(
        self,
        letter_box_def,
        output_width,
        output_height
    ):
        output = []

        ratio = letter_box_def["ratio"]
        fill_color = letter_box_def["fill_color"]
        f_red, f_green, f_blue, f_alpha = fill_color
        fill_color_hex = "{0:0>2X}{1:0>2X}{2:0>2X}".format(
            f_red, f_green, f_blue
        )
        fill_color_alpha = f_alpha

        line_thickness = letter_box_def["line_thickness"]
        line_color = letter_box_def["line_color"]
        l_red, l_green, l_blue, l_alpha = line_color
        line_color_hex = "{0:0>2X}{1:0>2X}{2:0>2X}".format(
            l_red, l_green, l_blue
        )
        line_color_alpha = l_alpha

        # test ratios and define if pillar or letter boxes
        output_ratio = float(output_width) / float(output_height)
        self.log.debug("Output ratio: {} LetterBox ratio: {}".format(
            output_ratio, ratio
        ))
        pillar = output_ratio > ratio
        need_mask = format(output_ratio, ".3f") != format(ratio, ".3f")
        if not need_mask:
            return []

        if not pillar:
            if fill_color_alpha > 0:
                top_box = (
                    "drawbox=0:0:{width}"
                    ":round(({height}-({width}/{ratio}))/2)"
                    ":t=fill:c={color}@{alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    color=fill_color_hex,
                    alpha=fill_color_alpha
                )

                bottom_box = (
                    "drawbox=0"
                    ":{height}-round(({height}-({width}/{ratio}))/2)"
                    ":{width}"
                    ":round(({height}-({width}/{ratio}))/2)"
                    ":t=fill:c={color}@{alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    color=fill_color_hex,
                    alpha=fill_color_alpha
                )
                output.extend([top_box, bottom_box])

            if line_color_alpha > 0 and line_thickness > 0:
                top_line = (
                    "drawbox=0"
                    ":round(({height}-({width}/{ratio}))/2)-{l_thick}"
                    ":{width}:{l_thick}:t=fill:c={l_color}@{l_alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    l_thick=line_thickness,
                    l_color=line_color_hex,
                    l_alpha=line_color_alpha
                )
                bottom_line = (
                    "drawbox=0"
                    ":{height}-round(({height}-({width}/{ratio}))/2)"
                    ":{width}:{l_thick}:t=fill:c={l_color}@{l_alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    l_thick=line_thickness,
                    l_color=line_color_hex,
                    l_alpha=line_color_alpha
                )
                output.extend([top_line, bottom_line])

        else:
            if fill_color_alpha > 0:
                left_box = (
                    "drawbox=0:0"
                    ":round(({width}-({height}*{ratio}))/2)"
                    ":{height}"
                    ":t=fill:c={color}@{alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    color=fill_color_hex,
                    alpha=fill_color_alpha
                )

                right_box = (
                    "drawbox="
                    "{width}-round(({width}-({height}*{ratio}))/2)"
                    ":0"
                    ":round(({width}-({height}*{ratio}))/2)"
                    ":{height}"
                    ":t=fill:c={color}@{alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    color=fill_color_hex,
                    alpha=fill_color_alpha
                )
                output.extend([left_box, right_box])

            if line_color_alpha > 0 and line_thickness > 0:
                left_line = (
                    "drawbox=round(({width}-({height}*{ratio}))/2)"
                    ":0:{l_thick}:{height}:t=fill:c={l_color}@{l_alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    l_thick=line_thickness,
                    l_color=line_color_hex,
                    l_alpha=line_color_alpha
                )

                right_line = (
                    "drawbox={width}-round(({width}-({height}*{ratio}))/2)"
                    ":0:{l_thick}:{height}:t=fill:c={l_color}@{l_alpha}"
                ).format(
                    width=output_width,
                    height=output_height,
                    ratio=ratio,
                    l_thick=line_thickness,
                    l_color=line_color_hex,
                    l_alpha=line_color_alpha
                )
                output.extend([left_line, right_line])

        return output

    def rescaling_filters(self, temp_data, output_def, new_repre):
        """Prepare vieo filters based on tags in new representation.

        It is possible to add letterboxes to output video or rescale to
        different resolution.

        During this preparation "resolutionWidth" and "resolutionHeight" are
        set to new representation.
        """
        filters = []

        # if reformat input video file is already reforamted from upstream
        reformat_in_baking = (
            "reformatted" in new_repre["tags"]
            # Backwards compatibility
            or "reformated" in new_repre["tags"]
        )
        self.log.debug("reformat_in_baking: `{}`".format(reformat_in_baking))

        # NOTE Skipped using instance's resolution
        full_input_path_single_file = temp_data["full_input_path_single_file"]
        try:
            streams = get_ffprobe_streams(
                full_input_path_single_file, self.log
            )
        except Exception as exc:
            raise AssertionError((
                "FFprobe couldn't read information about input file: \"{}\"."
                " Error message: {}"
            ).format(full_input_path_single_file, str(exc)))

        # Try to find first stream with defined 'width' and 'height'
        # - this is to avoid order of streams where audio can be as first
        # - there may be a better way (checking `codec_type`?)
        input_width = None
        input_height = None
        output_width = None
        output_height = None
        for stream in streams:
            if "width" in stream and "height" in stream:
                input_width = int(stream["width"])
                input_height = int(stream["height"])
                break

        # Get instance data
        pixel_aspect = temp_data["pixel_aspect"]
        if reformat_in_baking:
            self.log.debug((
                "Using resolution from input. It is already "
                "reformatted from upstream process"
            ))
            pixel_aspect = 1
            output_width = input_width
            output_height = input_height

        # Raise exception of any stream didn't define input resolution
        if input_width is None:
            raise AssertionError((
                "FFprobe couldn't read resolution from input file: \"{}\""
            ).format(full_input_path_single_file))

        # NOTE Setting only one of `width` or `height` is not allowed
        # - settings value can't have None but has value of 0
        output_width = output_def["width"] or output_width or None
        output_height = output_def["height"] or output_height or None

        # Force to use input resolution if output resolution was not defined
        #   in settings. Resolution from instance is not used when
        #   'use_input_res' is set to 'True'.
        use_input_res = False

        # Overscan color
        overscan_color_value = "black"
        overscan_color = output_def.get("overscan_color")
        if overscan_color:
            if len(overscan_color) == 3:
                bg_red, bg_green, bg_blue = overscan_color
            else:
                # Backwards compatibility
                bg_red, bg_green, bg_blue, _  = overscan_color

            overscan_color_value = "#{0:0>2X}{1:0>2X}{2:0>2X}".format(
                bg_red, bg_green, bg_blue
            )
        self.log.debug("Overscan color: `{}`".format(overscan_color_value))

        # Scale input to have proper pixel aspect ratio
        # - scale width by the pixel aspect ratio
        scale_pixel_aspect = output_def.get("scale_pixel_aspect", True)
        if scale_pixel_aspect and pixel_aspect != 1:
            # Change input width after pixel aspect
            input_width = int(input_width * pixel_aspect)
            use_input_res = True
            filters.append((
                "scale={}x{}:flags=lanczos".format(input_width, input_height)
            ))

        # Convert overscan value video filters
        overscan_crop = output_def.get("overscan_crop")
        overscan = OverscanCrop(
            input_width, input_height, overscan_crop, overscan_color_value
        )
        overscan_crop_filters = overscan.video_filters()
        # Add overscan filters to filters if are any and modify input
        #   resolution by it's values
        if overscan_crop_filters:
            filters.extend(overscan_crop_filters)
            # Change input resolution after overscan crop
            input_width = overscan.width()
            input_height = overscan.height()
            use_input_res = True

        # Make sure input width and height is not an odd number
        input_width_is_odd = bool(input_width % 2 != 0)
        input_height_is_odd = bool(input_height % 2 != 0)
        if input_width_is_odd or input_height_is_odd:
            # Add padding to input and make sure this filter is at first place
            filters.append("pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2")

            # Change input width or height as first filter will change them
            if input_width_is_odd:
                self.log.info((
                    "Converting input width from odd to even number. {} -> {}"
                ).format(input_width, input_width + 1))
                input_width += 1

            if input_height_is_odd:
                self.log.info((
                    "Converting input height from odd to even number. {} -> {}"
                ).format(input_height, input_height + 1))
                input_height += 1

        self.log.debug("pixel_aspect: `{}`".format(pixel_aspect))
        self.log.debug("input_width: `{}`".format(input_width))
        self.log.debug("input_height: `{}`".format(input_height))

        # Use instance resolution if output definition has not set it
        #   - use instance resolution only if there were not scale changes
        #       that may massivelly affect output 'use_input_res'
        if not use_input_res and output_width is None or output_height is None:
            output_width = temp_data["resolution_width"]
            output_height = temp_data["resolution_height"]

        # Use source's input resolution instance does not have set it.
        if output_width is None or output_height is None:
            self.log.debug("Using resolution from input.")
            output_width = input_width
            output_height = input_height

        output_width = int(output_width)
        output_height = int(output_height)

        # Make sure output width and height is not an odd number
        # When this can happen:
        # - if output definition has set width and height with odd number
        # - `instance.data` contain width and height with odd number
        if output_width % 2 != 0:
            self.log.warning((
                "Converting output width from odd to even number. {} -> {}"
            ).format(output_width, output_width + 1))
            output_width += 1

        if output_height % 2 != 0:
            self.log.warning((
                "Converting output height from odd to even number. {} -> {}"
            ).format(output_height, output_height + 1))
            output_height += 1

        self.log.debug(
            "Output resolution is {}x{}".format(output_width, output_height)
        )

        letter_box_def = output_def["letter_box"]
        letter_box_enabled = letter_box_def["enabled"]

        # Skip processing if resolution is same as input's and letterbox is
        # not set
        if (
            output_width == input_width
            and output_height == input_height
            and not letter_box_enabled
        ):
            self.log.debug(
                "Output resolution is same as input's"
                " and \"letter_box\" key is not set. Skipping reformat part."
            )
            new_repre["resolutionWidth"] = input_width
            new_repre["resolutionHeight"] = input_height
            return filters

        # scaling none square pixels and 1920 width
        if input_height != output_height or input_width != output_width:
            filters.extend([
                (
                    "scale={}x{}"
                    ":flags=lanczos"
                    ":force_original_aspect_ratio=decrease"
                ).format(output_width, output_height),
                "pad={}:{}:(ow-iw)/2:(oh-ih)/2:{}".format(
                    output_width, output_height,
                    overscan_color_value
                ),
                "setsar=1"
            ])

        # letter_box
        if letter_box_enabled:
            filters.extend(
                self.get_letterbox_filters(
                    letter_box_def,
                    output_width,
                    output_height
                )
            )

        new_repre["resolutionWidth"] = output_width
        new_repre["resolutionHeight"] = output_height

        return filters

    def lut_filters(self, new_repre, instance, input_args):
        """Add lut file to output ffmpeg filters."""
        filters = []
        # baking lut file application
        lut_path = instance.data.get("lutPath")
        if not lut_path or "bake-lut" not in new_repre["tags"]:
            return filters

        # Prepare path for ffmpeg argument
        lut_path = lut_path.replace("\\", "/").replace(":", "\\:")

        # Remove gamma from input arguments
        if "-gamma" in input_args:
            input_args.remove("-gamme")

        # Prepare filters
        filters.append("lut3d=file='{}'".format(lut_path))
        # QUESTION hardcoded colormatrix?
        filters.append("colormatrix=bt601:bt709")

        self.log.info("Added Lut to ffmpeg command.")

        return filters

    def families_from_instance(self, instance):
        """Returns all families of entered instance."""
        families = []
        family = instance.data.get("family")
        if family:
            families.append(family)

        for family in (instance.data.get("families") or tuple()):
            if family not in families:
                families.append(family)
        return families

    def families_filter_validation(self, families, output_families_filter):
        """Determines if entered families intersect with families filters.

        All family values are lowered to avoid unexpected results.
        """

        families_filter_lower = set(family.lower() for family in
                                    output_families_filter
                                    # Exclude empty filter values
                                    if family)
        if not families_filter_lower:
            return True
        return any(family.lower() in families_filter_lower
                   for family in families)

    def filter_output_defs(self, profile, product_name, families):
        """Return outputs matching input instance families.

        Output definitions without families filter are marked as valid.

        Args:
            profile (dict): Profile from presets matching current context.
            families (list): All families of current instance.
            product_name (str): Product name.

        Returns:
            dict[str, Any]: Containing all output definitions matching entered
                families.
        """
        filtered_outputs = {}
        outputs = profile.get("outputs")
        if not outputs:
            return filtered_outputs

        for output_def in outputs:
            filename_suffix = output_def["name"]
            output_filters = output_def.get("filter")
            # If no filter on output preset, skip filtering and add output
            # profile for farther processing
            if not output_filters:
                filtered_outputs[filename_suffix] = output_def
                continue

            families_filters = output_filters.get("families")
            if not self.families_filter_validation(families, families_filters):
                continue

            # Subsets name filters
            product_name_filters = [
                name_filter
                for name_filter in output_filters.get("product_names", [])
                # Skip empty strings
                if name_filter
            ]
            if product_name and product_name_filters:
                match = False
                for product_name_filter in product_name_filters:
                    compiled = re.compile(product_name_filter)
                    if compiled.search(product_name):
                        match = True
                        break

                if not match:
                    continue

            filtered_outputs[filename_suffix] = output_def

        return filtered_outputs

    def filter_outputs_by_custom_tags(self, outputs, custom_tags):
        """Filter output definitions by entered representation custom_tags.

        Output definitions without custom_tags filter are marked as invalid,
        only in case representation is having any custom_tags defined.

        Args:
            outputs (list): Contain list of output definitions from presets.
            custom_tags (list): Custom Tags of processed representation.

        Returns:
            list: Containing all output definitions matching entered tags.
        """

        filtered_outputs = []
        repre_c_tags_low = [tag.lower() for tag in (custom_tags or [])]
        for output_def in outputs:
            tag_filters = output_def.get("filter", {}).get("custom_tags")

            if not custom_tags and not tag_filters:
                # Definition is valid if both tags are empty
                valid = True

            elif not custom_tags or not tag_filters:
                # Invalid if one is empty
                valid = False

            else:
                # Check if output definition tags are in representation tags
                valid = False
                # lower all filter tags
                tag_filters_low = [tag.lower() for tag in tag_filters]
                # check if any repre tag is not in filter tags
                for tag in repre_c_tags_low:
                    if tag in tag_filters_low:
                        valid = True
                        break

            if valid:
                filtered_outputs.append(output_def)

        self.log.debug("__ filtered_outputs: {}".format(
            [_o["filename_suffix"] for _o in filtered_outputs]
        ))

        return filtered_outputs

    def add_video_filter_args(self, args, inserting_arg):
        """
        Fixing video filter arguments to be one long string

        Args:
            args (list): list of string arguments
            inserting_arg (str): string argument we want to add
                                 (without flag `-vf`)

        Returns:
            str: long joined argument to be added back to list of arguments

        """
        # find all video format settings
        vf_settings = [p for p in args
                       for v in ["-filter:v", "-vf"]
                       if v in p]
        self.log.debug("_ vf_settings: `{}`".format(vf_settings))

        # remove them from output args list
        for p in vf_settings:
            self.log.debug("_ remove p: `{}`".format(p))
            args.remove(p)
            self.log.debug("_ args: `{}`".format(args))

        # strip them from all flags
        vf_fixed = [p.replace("-vf ", "").replace("-filter:v ", "")
                    for p in vf_settings]

        self.log.debug("_ vf_fixed: `{}`".format(vf_fixed))
        vf_fixed.insert(0, inserting_arg)
        self.log.debug("_ vf_fixed: `{}`".format(vf_fixed))
        # create new video filter setting
        vf_back = "-vf " + ",".join(vf_fixed)

        return vf_back


class _OverscanValue(ABC):
    def __repr__(self):
        return "<{}> {}".format(self.__class__.__name__, str(self))

    @abstractmethod
    def copy(self):
        """Create a copy of object."""
        pass

    @abstractmethod
    def size_for(self, value):
        """Calculate new value for passed value."""
        pass


class PixValueExplicit(_OverscanValue):
    def __init__(self, value):
        self._value = int(value)

    def __str__(self):
        return "{}px".format(self._value)

    def copy(self):
        return PixValueExplicit(self._value)

    def size_for(self, value):
        if self._value == 0:
            return value
        return self._value


class PercentValueExplicit(_OverscanValue):
    def __init__(self, value):
        self._value = float(value)

    def __str__(self):
        return "{}%".format(abs(self._value))

    def copy(self):
        return PercentValueExplicit(self._value)

    def size_for(self, value):
        if self._value == 0:
            return value
        return int((value / 100) * self._value)


class PixValueRelative(_OverscanValue):
    def __init__(self, value):
        self._value = int(value)

    def __str__(self):
        sign = "-" if self._value < 0 else "+"
        return "{}{}px".format(sign, abs(self._value))

    def copy(self):
        return PixValueRelative(self._value)

    def size_for(self, value):
        return value + self._value


class PercentValueRelative(_OverscanValue):
    def __init__(self, value):
        self._value = float(value)

    def __str__(self):
        return "{}%".format(self._value)

    def copy(self):
        return PercentValueRelative(self._value)

    def size_for(self, value):
        if self._value == 0:
            return value

        offset = int((value / 100) * self._value)

        return value + offset


class PercentValueRelativeSource(_OverscanValue):
    def __init__(self, value, source_sign):
        self._value = float(value)
        if source_sign not in ("-", "+"):
            raise ValueError(
                "Invalid sign value \"{}\" expected \"-\" or \"+\"".format(
                    source_sign
                )
            )
        self._source_sign = source_sign

    def __str__(self):
        return "{}%{}".format(self._value, self._source_sign)

    def copy(self):
        return PercentValueRelativeSource(self._value, self._source_sign)

    def size_for(self, value):
        if self._value == 0:
            return value
        return int((value * 100) / (100 - self._value))


class OverscanCrop:
    """Helper class to read overscan string and calculate output resolution.

    It is possible to enter single value for both width and height, or
    two values for width and height. Overscan string may have a few variants.
    Each variant define output size for input size.

    ### Example
    For input size: 2200px

    | String   | Output | Description                                     |
    |----------|--------|-------------------------------------------------|
    | ""       | 2200px | Empty string does nothing.                      |
    | "10%"    | 220px  | Explicit percent size.                          |
    | "-10%"   | 1980px | Relative percent size (decrease).               |
    | "+10%"   | 2420px | Relative percent size (increase).               |
    | "-10%+"  | 2000px | Relative percent size to output size.           |
    | "300px"  | 300px  | Explicit output size cropped or expanded.       |
    | "-300px" | 1900px | Relative pixel size (decrease).                 |
    | "+300px" | 2500px | Relative pixel size (increase).                 |
    | "300"    | 300px  | Value without "%" and "px" is used as has "px". |

    Value without sign (+/-) in is always explicit and value with sign is
    relative. Output size for "200px" and "+200px" are not the same.
    Values "0", "0px" or "0%" are ignored.

    All values that cause output resolution smaller than 1 pixel are invalid.

    Value "-10%+" is a special case which says that input's resolution is
    bigger by 10% than expected output.

    It is possible to combine these variants to define different output for
    width and height.

    Resolution: 2000px 1000px

    | String        | Output        |
    |---------------|---------------|
    | "100px 120px" | 2100px 1120px |
    | "-10% -200px" | 1800px 800px  |
    """

    item_regex = re.compile(r"([\+\-])?([0-9]+)(.+)?")
    relative_source_regex = re.compile(r"%([\+\-])")

    def __init__(
        self, input_width, input_height, string_value, overscan_color=None
    ):
        # Make sure that is not None
        string_value = string_value or ""

        self.input_width = input_width
        self.input_height = input_height
        self.overscan_color = overscan_color

        width, height = self._convert_string_to_values(string_value)
        self._width_value = width
        self._height_value = height

        self._string_value = string_value

    def __str__(self):
        return "{}".format(self._string_value)

    def __repr__(self):
        return "<{}>".format(self.__class__.__name__)

    def width(self):
        """Calculated width."""
        return self._width_value.size_for(self.input_width)

    def height(self):
        """Calculated height."""
        return self._height_value.size_for(self.input_height)

    def video_filters(self):
        """FFmpeg video filters to achieve expected result.

        Filter may be empty, use "crop" filter, "pad" filter or combination of
        "crop" and "pad".

        Returns:
            list: FFmpeg video filters.
        """
        # crop=width:height:x:y - explicit start x, y position
        # crop=width:height     - x, y are related to center by width/height
        # pad=width:height:x:y  - explicit start x, y position
        # pad=width:height      - x, y are set to 0 by default

        width = self.width()
        height = self.height()

        output = []
        if self.input_width == width and self.input_height == height:
            return output

        # Make sure resolution has odd numbers
        if width % 2 == 1:
            width -= 1

        if height % 2 == 1:
            height -= 1

        if width <= self.input_width and height <= self.input_height:
            output.append("crop={}:{}".format(width, height))

        elif width >= self.input_width and height >= self.input_height:
            output.append(
                "pad={}:{}:(iw-ow)/2:(ih-oh)/2:{}".format(
                    width, height, self.overscan_color
                )
            )

        elif width > self.input_width and height < self.input_height:
            output.append("crop=iw:{}".format(height))
            output.append("pad={}:ih:(iw-ow)/2:(ih-oh)/2:{}".format(
                width, self.overscan_color
            ))

        elif width < self.input_width and height > self.input_height:
            output.append("crop={}:ih".format(width))
            output.append("pad=iw:{}:(iw-ow)/2:(ih-oh)/2:{}".format(
                height, self.overscan_color
            ))

        return output

    def _convert_string_to_values(self, orig_string_value):
        string_value = orig_string_value.strip().lower()
        if not string_value:
            return [PixValueRelative(0), PixValueRelative(0)]

        # Replace "px" (and spaces before) with single space
        string_value = re.sub(r"([ ]+)?px", " ", string_value)
        string_value = re.sub(r"([ ]+)%", "%", string_value)
        # Make sure +/- sign at the beginning of string is next to number
        string_value = re.sub(r"^([\+\-])[ ]+", r"\g<1>", string_value)
        # Make sure +/- sign in the middle has zero spaces before number under
        #   which belongs
        string_value = re.sub(
            r"[ ]([\+\-])[ ]+([0-9])",
            r" \g<1>\g<2>",
            string_value
        )
        string_parts = [
            part
            for part in string_value.split(" ")
            if part
        ]

        error_msg = "Invalid string for rescaling \"{}\"".format(
            orig_string_value
        )
        if 1 > len(string_parts) > 2:
            raise ValueError(error_msg)

        output = []
        for item in string_parts:
            groups = self.item_regex.findall(item)
            if not groups:
                raise ValueError(error_msg)

            relative_sign, value, ending = groups[0]
            if not relative_sign:
                if not ending:
                    output.append(PixValueExplicit(value))
                else:
                    output.append(PercentValueExplicit(value))
            else:
                source_sign_group = self.relative_source_regex.findall(ending)
                if not ending:
                    output.append(PixValueRelative(int(relative_sign + value)))

                elif source_sign_group:
                    source_sign = source_sign_group[0]
                    output.append(PercentValueRelativeSource(
                        float(relative_sign + value), source_sign
                    ))
                else:
                    output.append(
                        PercentValueRelative(float(relative_sign + value))
                    )

        if len(output) == 1:
            width = output.pop(0)
            height = width.copy()
        else:
            width, height = output

        return width, height
