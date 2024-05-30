import os
import opentimelineio
from opentimelineio.exceptions import UnsupportedSchemaError


import pyblish.api
from ayon_core.pipeline import PublishValidationError


class ValidateEditorialPackage(pyblish.api.InstancePlugin):
    """Checks that published folder contains all resources from otio

    Currently checks only by file names and expects flat structure.
    It ignores path to resources in otio file as folder might be dragged in and
    published from different location than it was created.
    """

    label = "Validate Editorial Package"
    order = pyblish.api.ValidatorOrder - 0.49

    hosts = ["traypublisher"]
    families = ["editorial_pkg"]

    def process(self, instance):
        editorial_pkg_data = instance.data.get("editorial_pkg")
        if not editorial_pkg_data:
            raise PublishValidationError("Editorial package not collected")

        folder_path = editorial_pkg_data["folder_path"]

        otio_path = editorial_pkg_data["otio_path"]
        if not otio_path:
            raise PublishValidationError(
                f"Folder {folder_path} missing otio file")

        resource_paths = editorial_pkg_data["resource_paths"]

        resource_file_names = {os.path.basename(path)
                               for path in resource_paths}

        try:
            otio_data = opentimelineio.adapters.read_from_file(otio_path)
        except UnsupportedSchemaError as e:
            raise PublishValidationError(
                f"Unsupported schema in otio file '{otio_path}'."
                "Version of your OpenTimelineIO library is too old."
                "Please update it to the latest version."
                f"Current version is '{opentimelineio.__version__}', "
                "but required is at least 0.16.0."
            ) from e

        target_urls = self._get_all_target_urls(otio_data)
        missing_files = set()
        for target_url in target_urls:
            target_basename = os.path.basename(target_url)
            if target_basename not in resource_file_names:
                missing_files.add(target_basename)

        if missing_files:
            raise PublishValidationError(
                f"Otio file contains missing files `{missing_files}`.\n\n"
                f"Please add them to `{folder_path}` and republish.")

        instance.data["editorial_pkg"]["otio_data"] = otio_data

    def _get_all_target_urls(self, otio_data):
        target_urls = []

        # Iterate through tracks, clips, or other elements
        for track in otio_data.tracks:
            for clip in track:
                # Check if the clip has a media reference
                if clip.media_reference is not None:
                    # Access the target_url from the media reference
                    target_url = clip.media_reference.target_url
                    if target_url:
                        target_urls.append(target_url)

        return target_urls
