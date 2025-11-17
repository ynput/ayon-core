import os
import copy
import clique
import pyblish.api

from ayon_core.pipeline import (
    publish,
    get_temp_dir
)
from ayon_core.lib import (
    is_oiio_supported,
    get_oiio_tool_args,
    run_subprocess
)
from ayon_core.lib.profiles_filtering import filter_profiles


class ExtractOIIOPostProcess(publish.Extractor):
    """Process representations through `oiiotool` with profile defined
    settings so that e.g. color space conversions can be applied or images
    could be converted to scanline, resized, etc. regardless of colorspace
    data.
    """

    label = "OIIO Post Process"
    order = pyblish.api.ExtractorOrder + 0.020

    settings_category = "core"

    optional = True

    # Supported extensions
    supported_exts = {"exr", "jpg", "jpeg", "png", "dpx"}

    # Configurable by Settings
    profiles = None
    options = None

    def process(self, instance):
        if not self.profiles:
            self.log.debug("No profiles present for OIIO Post Process")
            return

        if "representations" not in instance.data:
            self.log.debug("No representations, skipping.")
            return

        if not is_oiio_supported():
            self.log.warning("OIIO not supported, no transcoding possible.")
            return

        profile = self._get_profile(
            instance
        )
        if not profile:
            return

        profile_output_defs = profile["outputs"]
        new_representations = []
        for idx, repre in enumerate(list(instance.data["representations"])):
            self.log.debug("repre ({}): `{}`".format(idx + 1, repre["name"]))
            if not self._repre_is_valid(repre):
                continue

            # Get representation files to convert
            if isinstance(repre["files"], list):
                repre_files_to_convert = copy.deepcopy(repre["files"])
            else:
                repre_files_to_convert = [repre["files"]]

            added_representations = False
            added_review = False

            # Process each output definition
            for output_def in profile_output_defs:

                # Local copy to avoid accidental mutable changes
                files_to_convert = list(repre_files_to_convert)

                output_name = output_def["name"]
                new_repre = copy.deepcopy(repre)

                original_staging_dir = new_repre["stagingDir"]
                new_staging_dir = get_temp_dir(
                    project_name=instance.context.data["projectName"],
                    use_local_temp=True,
                )
                new_repre["stagingDir"] = new_staging_dir

                output_extension = output_def["extension"]
                output_extension = output_extension.replace('.', '')
                self._rename_in_representation(new_repre,
                                               files_to_convert,
                                               output_name,
                                               output_extension)

                sequence_files = self._translate_to_sequence(files_to_convert)
                self.log.debug("Files to convert: {}".format(sequence_files))
                for file_name in sequence_files:
                    if isinstance(file_name, clique.Collection):
                        # Convert to filepath that can be directly converted
                        # by oiio like `frame.1001-1025%04d.exr`
                        file_name: str = file_name.format(
                            "{head}{range}{padding}{tail}"
                        )

                    self.log.debug("Transcoding file: `{}`".format(file_name))
                    input_path = os.path.join(original_staging_dir,
                                              file_name)
                    output_path = self._get_output_file_path(input_path,
                                                             new_staging_dir,
                                                             output_extension)

                    # TODO: Support formatting with dynamic keys from the
                    #  representation, like e.g. colorspace config, display,
                    #  view, etc.
                    input_arguments: list[str] = output_def.get(
                        "input_arguments", []
                    )
                    output_arguments: list[str] = output_def.get(
                        "output_arguments", []
                    )

                    # Prepare subprocess arguments
                    oiio_cmd = get_oiio_tool_args(
                        "oiiotool",
                        *input_arguments,
                        input_path,
                        *output_arguments,
                        "-o",
                        output_path
                    )

                    self.log.debug(
                        "Conversion command: {}".format(" ".join(oiio_cmd)))
                    run_subprocess(oiio_cmd, logger=self.log)

                # cleanup temporary transcoded files
                for file_name in new_repre["files"]:
                    transcoded_file_path = os.path.join(new_staging_dir,
                                                        file_name)
                    instance.context.data["cleanupFullPaths"].append(
                        transcoded_file_path)

                custom_tags = output_def.get("custom_tags")
                if custom_tags:
                    if new_repre.get("custom_tags") is None:
                        new_repre["custom_tags"] = []
                    new_repre["custom_tags"].extend(custom_tags)

                # Add additional tags from output definition to representation
                if new_repre.get("tags") is None:
                    new_repre["tags"] = []
                for tag in output_def["tags"]:
                    if tag not in new_repre["tags"]:
                        new_repre["tags"].append(tag)

                    if tag == "review":
                        added_review = True

                # If there is only 1 file outputted then convert list to
                # string, because that'll indicate that it is not a sequence.
                if len(new_repre["files"]) == 1:
                    new_repre["files"] = new_repre["files"][0]

                # If the source representation has "review" tag, but it's not
                # part of the output definition tags, then both the
                # representations will be transcoded in ExtractReview and
                # their outputs will clash in integration.
                if "review" in repre.get("tags", []):
                    added_review = True

                new_representations.append(new_repre)
                added_representations = True

            if added_representations:
                self._mark_original_repre_for_deletion(
                    repre, profile, added_review
                )

            tags = repre.get("tags") or []
            if "delete" in tags and "thumbnail" not in tags:
                instance.data["representations"].remove(repre)

        instance.data["representations"].extend(new_representations)

    def _rename_in_representation(self, new_repre, files_to_convert,
                                  output_name, output_extension):
        """Replace old extension with new one everywhere in representation.

        Args:
            new_repre (dict)
            files_to_convert (list): of filenames from repre["files"],
                standardized to always list
            output_name (str): key of output definition from Settings,
                if "<passthrough>" token used, keep original repre name
            output_extension (str): extension from output definition
        """
        if output_name != "passthrough":
            new_repre["name"] = output_name
        if not output_extension:
            return

        new_repre["ext"] = output_extension
        new_repre["outputName"] = output_name

        renamed_files = []
        for file_name in files_to_convert:
            file_name, _ = os.path.splitext(file_name)
            file_name = '{}.{}'.format(file_name,
                                       output_extension)
            renamed_files.append(file_name)
        new_repre["files"] = renamed_files

    def _translate_to_sequence(self, files_to_convert):
        """Returns original list or a clique.Collection of a sequence.

        Uses clique to find frame sequence Collection.
        If sequence not found, it returns original list.

        Args:
            files_to_convert (list): list of file names
        Returns:
            list[str | clique.Collection]: List of filepaths or a list
                of Collections (usually one, unless there are holes)
        """
        pattern = [clique.PATTERNS["frames"]]
        collections, _ = clique.assemble(
            files_to_convert, patterns=pattern,
            assume_padded_when_ambiguous=True)
        if collections:
            if len(collections) > 1:
                raise ValueError(
                    "Too many collections {}".format(collections))

            collection = collections[0]
            # TODO: Technically oiiotool supports holes in the sequence as well
            #  using the dedicated --frames argument to specify the frames.
            #  We may want to use that too so conversions of sequences with
            #  holes will perform faster as well.
            # Separate the collection so that we have no holes/gaps per
            # collection.
            return collection.separate()

        return files_to_convert

    def _get_output_file_path(self, input_path, output_dir,
                              output_extension):
        """Create output file name path."""
        file_name = os.path.basename(input_path)
        file_name, input_extension = os.path.splitext(file_name)
        if not output_extension:
            output_extension = input_extension.replace(".", "")
        new_file_name = '{}.{}'.format(file_name,
                                       output_extension)
        return os.path.join(output_dir, new_file_name)

    def _get_profile(self, instance):
        """Returns profile if it should process this instance."""
        host_name = instance.context.data["hostName"]
        product_type = instance.data["productType"]
        product_name = instance.data["productName"]
        task_data = instance.data["anatomyData"].get("task", {})
        task_name = task_data.get("name")
        task_type = task_data.get("type")
        filtering_criteria = {
            "hosts": host_name,
            "product_types": product_type,
            "product_names": product_name,
            "task_names": task_name,
            "task_types": task_type,
        }
        profile = filter_profiles(self.profiles, filtering_criteria,
                                  logger=self.log)

        if not profile:
            self.log.debug((
              "Skipped instance. None of profiles in presets are for"
              " Host: \"{}\" | Product types: \"{}\" | Product names: \"{}\""
              " | Task name \"{}\" | Task type \"{}\""
            ).format(
                host_name, product_type, product_name, task_name, task_type
            ))

        return profile

    def _repre_is_valid(self, repre) -> bool:
        """Validation if representation should be processed.

        Args:
            repre (dict): Representation which should be checked.

        Returns:
            bool: False if can't be processed else True.
        """
        if repre.get("ext") not in self.supported_exts:
            self.log.debug((
                "Representation '{}' has unsupported extension: '{}'. Skipped."
            ).format(repre["name"], repre.get("ext")))
            return False

        if not repre.get("files"):
            self.log.debug((
                "Representation '{}' has empty files. Skipped."
            ).format(repre["name"]))
            return False

        return True

    def _mark_original_repre_for_deletion(self, repre, profile, added_review):
        """If new transcoded representation created, delete old."""
        if not repre.get("tags"):
            repre["tags"] = []

        delete_original = profile["delete_original"]

        if delete_original:
            if "delete" not in repre["tags"]:
                repre["tags"].append("delete")

        if added_review and "review" in repre["tags"]:
            repre["tags"].remove("review")
