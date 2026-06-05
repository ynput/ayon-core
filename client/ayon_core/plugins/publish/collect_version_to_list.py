from __future__ import annotations

import pyblish.api
from ayon_core.lib import filter_profiles
from ayon_core.pipeline.structures import ListConfig


class CollectVersionToList(pyblish.api.InstancePlugin):
    """Collect Version to List."""

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Version to List"
    settings_category = "core"

    profiles = []

    def process(self, instance):
        if "versionLists" in instance.data:
            version_lists = instance.data["versionLists"]
            self.log.debug(f"Version lists already collected: {version_lists}")
            return

        version_lists: list[ListConfig] = []
        instance.data["versionLists"] = version_lists

        profile = self._get_profile_for_instance(instance)
        if not profile:
            self.log.debug(f"No profile found for instance {instance}")
            return

        name = profile["list_name"]
        version_lists.append(
            ListConfig(
                name=name,
                parent_folders=profile["parent_folders"],
                list_type=profile["list_type"],
            )
        )
        self.log.debug(f"Collected version lists: {version_lists}")

    def _get_profile_for_instance(
        self,
        instance: pyblish.api.Instance
    ) -> dict | None:
        """Returns profile for the given instance."""
        host_name = instance.context.data["hostName"]
        product_base_type = instance.data.get("productBaseType")
        if not product_base_type:
            product_base_type = instance.data["productType"]
        product_name = instance.data["productName"]
        task_data = instance.data["anatomyData"].get("task", {})
        task_name = task_data.get("name")
        task_type = task_data.get("type")
        filtering_criteria = {
            "host_names": host_name,
            "product_base_types": product_base_type,
            "product_names": product_name,
            "task_names": task_name,
            "task_types": task_type,
        }
        profile = filter_profiles(
            self.profiles,
            filtering_criteria,
            logger=self.log
        )

        if not profile:
            self.log.debug(
                "Skipped instance. None of profiles in presets are for"
                f' Host name: "{host_name}"'
                f' | Product base type: "{product_base_type}"'
                f' | Product name: "{product_name}"'
                f' | Task name "{task_name}"'
                f' | Task type "{task_type}"'
            )
            return None

        return profile
