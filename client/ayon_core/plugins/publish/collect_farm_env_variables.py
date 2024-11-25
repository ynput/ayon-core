import os

import pyblish.api

from ayon_core.pipeline.publish import FARM_JOB_ENV_DATA_KEY


class CollectCoreJobEnvVars(pyblish.api.ContextPlugin):
    """Collect set of environment variables to submit with deadline jobs"""
    order = pyblish.api.CollectorOrder - 0.45
    label = "AYON core Farm Environment Variables"
    targets = ["local"]

    ENV_KEYS = [
        # AYON
        "AYON_BUNDLE_NAME",
        "AYON_DEFAULT_SETTINGS_VARIANT",
        "AYON_PROJECT_NAME",
        "AYON_FOLDER_PATH",
        "AYON_TASK_NAME",
        "AYON_APP_NAME",
        "AYON_WORKDIR",
        "AYON_APP_NAME",
        "AYON_LOG_NO_COLORS",
        "AYON_IN_TESTS",
        "IS_TEST",  # backwards compatibility
    ]

    def process(self, context):
        env = context.data.setdefault(FARM_JOB_ENV_DATA_KEY, {})
        for key in [
            # AYON
            "AYON_BUNDLE_NAME",
            "AYON_DEFAULT_SETTINGS_VARIANT",
            "AYON_PROJECT_NAME",
            "AYON_FOLDER_PATH",
            "AYON_TASK_NAME",
            "AYON_WORKDIR",
            "AYON_LOG_NO_COLORS",
            "AYON_IN_TESTS",
            # backwards compatibility
            "IS_TEST",
        ]:
            value = os.getenv(key)
            if value:
                self.log.debug(f"Setting job env: {key}: {value}")
                env[key] = value

