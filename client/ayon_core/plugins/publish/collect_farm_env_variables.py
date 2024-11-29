import os

import pyblish.api

from ayon_core.lib import get_ayon_username
from ayon_core.pipeline.publish import FARM_JOB_ENV_DATA_KEY


class CollectCoreJobEnvVars(pyblish.api.ContextPlugin):
    """Collect set of environment variables to submit with deadline jobs"""
    order = pyblish.api.CollectorOrder - 0.45
    label = "AYON core Farm Environment Variables"
    targets = ["local"]

    def process(self, context):
        env = context.data.setdefault(FARM_JOB_ENV_DATA_KEY, {})

        # Disable colored logs on farm
        for key, value in (
            ("AYON_LOG_NO_COLORS", "1"),
            ("AYON_PROJECT_NAME", context.data["projectName"]),
            ("AYON_FOLDER_PATH", context.data.get("folderPath")),
            ("AYON_TASK_NAME", context.data.get("task")),
            # NOTE we should use 'context.data["user"]' but that has higher
            #   order.
            ("AYON_USERNAME", get_ayon_username()),
        ):
            if value:
                self.log.debug(f"Setting job env: {key}: {value}")
                env[key] = value

        for key in [
            "AYON_BUNDLE_NAME",
            "AYON_DEFAULT_SETTINGS_VARIANT",
            "AYON_IN_TESTS",
            # NOTE Not sure why workdir is needed?
            "AYON_WORKDIR",
        ]:
            value = os.getenv(key)
            if value:
                self.log.debug(f"Setting job env: {key}: {value}")
                env[key] = value

