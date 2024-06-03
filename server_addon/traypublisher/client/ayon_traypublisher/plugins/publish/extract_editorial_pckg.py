import copy
import os.path
import subprocess

import opentimelineio

import pyblish.api

from ayon_core.lib import  get_ffmpeg_tool_args, run_subprocess
from ayon_core.pipeline import publish


class ExtractEditorialPckgConversion(publish.Extractor):
    """Replaces movie paths in otio file with publish rootless

    Prepares movie resources for integration (adds them to `transfers`).
    Converts .mov files according to output definition.
    """

    label = "Extract Editorial Package"
    order = pyblish.api.ExtractorOrder - 0.45
    hosts = ["traypublisher"]
    families = ["editorial_pkg"]

    def process(self, instance):
        editorial_pkg_data = instance.data.get("editorial_pkg")

        otio_path = editorial_pkg_data["otio_path"]
        otio_basename = os.path.basename(otio_path)
        staging_dir = self.staging_dir(instance)

        editorial_pkg_repre = {
            'name': "editorial_pkg",
            'ext': "otio",
            'files': otio_basename,
            "stagingDir": staging_dir,
        }
        otio_staging_path = os.path.join(staging_dir, otio_basename)

        instance.data["representations"].append(editorial_pkg_repre)

        publish_resource_folder = self._get_publish_resource_folder(instance)
        resource_paths = editorial_pkg_data["resource_paths"]
        transfers = self._get_transfers(resource_paths,
                                        publish_resource_folder)

        project_settings = instance.context.data["project_settings"]
        output_def = (project_settings["traypublisher"]
                                      ["publish"]
                                      ["ExtractEditorialPckgConversion"]
                                      ["output"])

        conversion_enabled = (instance.data["creator_attributes"]
                                           ["conversion_enabled"])

        if conversion_enabled and output_def["ext"]:
            transfers = self._convert_resources(output_def, transfers)

        instance.data["transfers"] = transfers

        source_to_rootless = self._get_resource_path_mapping(instance,
                                                             transfers)

        otio_data = editorial_pkg_data["otio_data"]
        otio_data = self._replace_target_urls(otio_data, source_to_rootless)

        opentimelineio.adapters.write_to_file(otio_data, otio_staging_path)

        self.log.info("Added Editorial Package representation: {}".format(
            editorial_pkg_repre))

    def _get_publish_resource_folder(self, instance):
        """Calculates publish folder and create it."""
        publish_path = self._get_published_path(instance)
        publish_folder = os.path.dirname(publish_path)
        publish_resource_folder = os.path.join(publish_folder, "resources")

        if not os.path.exists(publish_resource_folder):
            os.makedirs(publish_resource_folder, exist_ok=True)
        return publish_resource_folder

    def _get_resource_path_mapping(self, instance, transfers):
        """Returns dict of {source_mov_path: rootless_published_path}."""
        replace_paths = {}
        anatomy = instance.context.data["anatomy"]
        for source, destination in transfers:
            rootless_path = self._get_rootless(anatomy, destination)
            source_file_name = os.path.basename(source)
            replace_paths[source_file_name] = rootless_path
        return replace_paths

    def _get_transfers(self, resource_paths, publish_resource_folder):
        """Returns list of tuples (source, destination) with movie paths."""
        transfers = []
        for res_path in resource_paths:
            res_basename = os.path.basename(res_path)
            pub_res_path = os.path.join(publish_resource_folder, res_basename)
            transfers.append((res_path, pub_res_path))
        return transfers

    def _replace_target_urls(self, otio_data, replace_paths):
        """Replace original movie paths with published rootless ones."""
        for track in otio_data.tracks:
            for clip in track:
                # Check if the clip has a media reference
                if clip.media_reference is not None:
                    # Access the target_url from the media reference
                    target_url = clip.media_reference.target_url
                    if not target_url:
                        continue
                    file_name = os.path.basename(target_url)
                    replace_path = replace_paths.get(file_name)
                    if replace_path:
                        clip.media_reference.target_url = replace_path
                        if clip.name == file_name:
                            clip.name = os.path.basename(replace_path)

        return otio_data

    def _get_rootless(self, anatomy, path):
        """Try to find rootless {root[work]} path from `path`"""
        success, rootless_path = anatomy.find_root_template_from_path(
            path)
        if not success:
            # `rootless_path` is not set to `output_dir` if none of roots match
            self.log.warning(
               f"Could not find root path for remapping '{path}'."
            )
            rootless_path = path

        return rootless_path

    def _get_published_path(self, instance):
        """Calculates expected `publish` folder"""
        # determine published path from Anatomy.
        template_data = instance.data.get("anatomyData")
        rep = instance.data["representations"][0]
        template_data["representation"] = rep.get("name")
        template_data["ext"] = rep.get("ext")
        template_data["comment"] = None

        anatomy = instance.context.data["anatomy"]
        template_data["root"] = anatomy.roots
        template = anatomy.get_template_item("publish", "default", "path")
        template_filled = template.format_strict(template_data)
        return os.path.normpath(template_filled)

    def _convert_resources(self, output_def, transfers):
        """Converts all resource files to configured format."""
        out_extension = output_def["ext"]
        if not out_extension:
            self.log.warning("No output extension configured in "
               "ayon+settings://traypublisher/publish/ExtractEditorialPckgConversion")  # noqa
            return transfers

        final_transfers = []
        out_def_ffmpeg_args = output_def["ffmpeg_args"]
        ffmpeg_input_args = [
            value.strip()
            for value in out_def_ffmpeg_args["input"]
            if value.strip()
        ]
        ffmpeg_video_filters = [
            value.strip()
            for value in out_def_ffmpeg_args["video_filters"]
            if value.strip()
        ]
        ffmpeg_audio_filters = [
            value.strip()
            for value in out_def_ffmpeg_args["audio_filters"]
            if value.strip()
        ]
        ffmpeg_output_args = [
            value.strip()
            for value in out_def_ffmpeg_args["output"]
            if value.strip()
        ]
        ffmpeg_input_args = self._split_ffmpeg_args(ffmpeg_input_args)

        generic_args = [
            subprocess.list2cmdline(get_ffmpeg_tool_args("ffmpeg"))
        ]
        generic_args.extend(ffmpeg_input_args)
        if ffmpeg_video_filters:
            generic_args.append("-filter:v")
            generic_args.append(
                "\"{}\"".format(",".join(ffmpeg_video_filters)))

        if ffmpeg_audio_filters:
            generic_args.append("-filter:a")
            generic_args.append(
                "\"{}\"".format(",".join(ffmpeg_audio_filters)))

        for source, destination in transfers:
            base_name = os.path.basename(destination)
            file_name, ext = os.path.splitext(base_name)
            dest_path = os.path.join(os.path.dirname(destination),
                                     f"{file_name}.{out_extension}")
            final_transfers.append((source, dest_path))

            all_args = copy.deepcopy(generic_args)
            all_args.append(f"-i \"{source}\"")
            all_args.extend(ffmpeg_output_args)  # order matters
            all_args.append(f"\"{dest_path}\"")
            subprcs_cmd = " ".join(all_args)

            # run subprocess
            self.log.debug("Executing: {}".format(subprcs_cmd))
            run_subprocess(subprcs_cmd, shell=True, logger=self.log)
        return final_transfers

    def _split_ffmpeg_args(self, in_args):
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
