"""Collects published version of workfile and increments it.

For synchronization of published image and workfile version it is required
to store workfile version from workfile file name in context.data["version"].
In remote publishing this name is unreliable (artist might not follow naming
convention etc.), last published workfile version for particular workfile
product is used instead.

This plugin runs only in remote publishing (eg. Webpublisher).

Requires:
    context.data["folderEntity"]

Provides:
    context["version"] - incremented latest published workfile version
"""

import pyblish.api
import ayon_api

from ayon_core.pipeline.version_start import get_versioning_start


class CollectPublishedVersion(pyblish.api.ContextPlugin):
    """Collects published version of workfile and increments it."""

    order = pyblish.api.CollectorOrder + 0.190
    label = "Collect published version"
    hosts = ["photoshop"]
    targets = ["automated"]

    def process(self, context):
        workfile_product_name = None
        for instance in context:
            if instance.data["productType"] == "workfile":
                workfile_product_name = instance.data["productName"]
                break

        if not workfile_product_name:
            self.log.warning("No workfile instance found, "
                             "synchronization of version will not work.")
            return

        project_name = context.data["projectName"]
        folder_id = context.data["folderEntity"]["id"]

        version_entity = ayon_api.get_last_version_by_product_name(
            project_name, workfile_product_name, folder_id
        )

        if version_entity:
            version_int = int(version_entity["version"]) + 1
        else:
            version_int = get_versioning_start(
                project_name,
                "photoshop",
                task_name=context.data["task"],
                task_type=context.data["taskType"],
                project_settings=context.data["project_settings"]
            )

        self.log.debug(f"Setting {version_int} to context.")
        context.data["version"] = version_int
