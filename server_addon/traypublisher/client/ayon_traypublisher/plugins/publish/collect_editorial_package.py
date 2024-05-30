"""Produces instance.data["editorial_pkg"] data used during integration.

Requires:
    instance.data["creator_attributes"]["path"] - from creator

Provides:
    instance -> editorial_pkg (dict):
                    folder_path (str)
                    otio_path   (str) - from dragged folder
                    resource_paths (list)

"""
import os

import pyblish.api

from ayon_core.lib.transcoding import VIDEO_EXTENSIONS


class CollectEditorialPackage(pyblish.api.InstancePlugin):
    """Collects path to OTIO file and resources"""

    label = "Collect Editorial Package"
    order = pyblish.api.CollectorOrder - 0.1

    hosts = ["traypublisher"]
    families = ["editorial_pkg"]

    def process(self, instance):
        folder_path = instance.data["creator_attributes"]["folder_path"]
        if not folder_path or not os.path.exists(folder_path):
            self.log.info((
                "Instance doesn't contain collected existing folder path."
            ))
            return

        instance.data["editorial_pkg"] = {}
        instance.data["editorial_pkg"]["folder_path"] = folder_path

        otio_path, resource_paths = (
            self._get_otio_and_resource_paths(folder_path))

        instance.data["editorial_pkg"]["otio_path"] = otio_path
        instance.data["editorial_pkg"]["resource_paths"] = resource_paths

    def _get_otio_and_resource_paths(self, folder_path):
        otio_path = None
        resource_paths = []

        file_names = os.listdir(folder_path)
        for filename in file_names:
            _, ext = os.path.splitext(filename)
            file_path = os.path.join(folder_path, filename)
            if ext == ".otio":
                otio_path = file_path
            elif ext in VIDEO_EXTENSIONS:
                resource_paths.append(file_path)
        return otio_path, resource_paths
