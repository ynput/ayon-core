"""
Requires:
    context     -> anatomy
    context     -> anatomyData

Provides:
    instance    -> publishDir
    instance    -> resourcesDir
"""

import os
import copy

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishError,
    get_publish_template_object,
)


class CollectResourcesPath(pyblish.api.InstancePlugin):
    """Generate directory path where the files and resources will be stored.

    Collects folder name and file name from files, if exists, for in-situ
    publishing.
    """

    label = "Collect Resources Path"
    order = pyblish.api.CollectorOrder + 0.495
    families = ["*"]

    def process(self, instance):
        template_data = copy.deepcopy(instance.data["anatomyData"])

        # This is for cases of Deprecated anatomy without `folder`
        # TODO remove when all clients have solved this issue
        template_data.update({"frame": "FRAME_TEMP", "representation": "TEMP"})

        publish_template = get_publish_template_object(
            instance, logger=self.log
        )["directory"]

        if "{originalDirname}" in publish_template:
            original_directory = instance.data.get("originalDirname")
            if not original_directory:
                original_directory = instance.data.get("stagingDir")

            if not original_directory:
                raise PublishError(
                    "Publish template requires 'originalDirname'"
                    " but 'originalDirname' is not set on instance"
                    " and 'stagingDir' is not yet filled."
                )

            template_data["originalDirname"] = original_directory

        publish_folder = os.path.normpath(
            publish_template.format_strict(template_data)
        )
        resources_folder = os.path.join(publish_folder, "resources")

        instance.data["publishDir"] = publish_folder
        instance.data["resourcesDir"] = resources_folder

        self.log.debug("publishDir: \"{}\"".format(publish_folder))
        self.log.debug("resourcesDir: \"{}\"".format(resources_folder))
