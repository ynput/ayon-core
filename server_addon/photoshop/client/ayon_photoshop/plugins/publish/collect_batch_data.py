"""Parses batch context from json and continues in publish process.

Provides:
    context -> Loaded batch file.
        - folderPath
        - task  (task name)
        - taskType
        - project_name
        - variant

Code is practically copy of `openype/hosts/webpublish/collect_batch_data` as
webpublisher should be eventually ejected as an addon, eg. mentioned plugin
shouldn't be pushed into general publish plugins.
"""

import os

import pyblish.api

from ayon_webpublisher.lib import (
    get_batch_context_info,
    parse_json
)
from ayon_core.lib import is_in_tests


class CollectBatchData(pyblish.api.ContextPlugin):
    """Collect batch data from json stored in 'AYON_PUBLISH_DATA' env dir.

    The directory must contain 'manifest.json' file where batch data should be
    stored.
    """
    # must be really early, context values are only in json file
    order = pyblish.api.CollectorOrder - 0.495
    label = "Collect batch data"
    hosts = ["photoshop"]
    targets = ["webpublish"]

    def process(self, context):
        self.log.info("CollectBatchData")
        batch_dir = (
            os.environ.get("AYON_PUBLISH_DATA")
            or os.environ.get("OPENPYPE_PUBLISH_DATA")
        )
        if is_in_tests():
            self.log.debug("Automatic testing, no batch data, skipping")
            return

        assert batch_dir, (
            "Missing `AYON_PUBLISH_DATA`")

        assert os.path.exists(batch_dir), \
            "Folder {} doesn't exist".format(batch_dir)

        project_name = os.environ.get("AYON_PROJECT_NAME")
        if project_name is None:
            raise AssertionError(
                "Environment `AYON_PROJECT_NAME` was not found."
                "Could not set project `root` which may cause issues."
            )

        batch_data = parse_json(os.path.join(batch_dir, "manifest.json"))

        context.data["batchDir"] = batch_dir
        context.data["batchData"] = batch_data

        folder_path, task_name, task_type = get_batch_context_info(
            batch_data["context"]
        )

        os.environ["AYON_FOLDER_PATH"] = folder_path
        os.environ["AYON_TASK_NAME"] = task_name

        context.data["folderPath"] = folder_path
        context.data["task"] = task_name
        context.data["taskType"] = task_type
        context.data["project_name"] = project_name
        context.data["variant"] = batch_data["variant"]
