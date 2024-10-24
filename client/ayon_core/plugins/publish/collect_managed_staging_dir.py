"""
Requires:
    anatomy


Provides:
    instance.data     -> stagingDir (folder path)
                      -> stagingDir_persistent (bool)
"""

import pyblish.api

from ayon_core.pipeline.publish import get_instance_staging_dir


class CollectManagedStagingDir(pyblish.api.InstancePlugin):
    """Apply matching Staging Dir profile to a instance.

    Apply Staging dir via profiles could be useful in specific use cases
    where is desirable to have temporary renders in specific,
    persistent folders, could be on disks optimized for speed for example.

    It is studio's responsibility to clean up obsolete folders with data.

    Location of the folder is configured in:
        `ayon+anatomy://_/templates/staging`.

    Which family/task type/subset is applicable is configured in:
        `ayon+settings://core/tools/publish/custom_staging_dir_profiles`
    """

    label = "Collect Managed Staging Directory"
    order = pyblish.api.CollectorOrder + 0.4990

    def process(self, instance):

        staging_dir_path = get_instance_staging_dir(instance)
        persistance = instance.data.get("stagingDir_persistent", False)

        self.log.info((
            f"Instance staging dir was set to `{staging_dir_path}` "
            f"and persistence is set to `{persistance}`"
        ))
