from __future__ import annotations

import platform
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pyblish.api
from ayon_core.lib import StringTemplate, filter_profiles

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


@dataclass
class ListConfig:
    """Define a list."""
    name: str
    parent_folders: list[str] | None = None
    is_review_list: bool = False


class CollectVersionToList(pyblish.api.InstancePlugin):
    """Collect Version to List."""

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Version to List"

    profiles = []

    def process(self, instance):
        profile = self._get_config_from_profile(instance)
        if not profile:
            self.log.debug(f"No profile found for instance {instance}")
            return

        anatomy_data: dict[str, Any] = instance.data["anatomyData"]
        anatomy: Anatomy = instance.context.data["anatomy"]
        name_template = profile["name_template"]
        template_data = deepcopy(anatomy_data)
        template_data.update({
            "root": anatomy.roots,
            "platform": platform.system().lower(),
        })

        list_name = StringTemplate.format_strict_template(
            name_template, template_data)

        version_lists: list[ListConfig] = instance.data.setdefault(
            "versionLists", [])
        version_lists.append(
            ListConfig(
                name=list_name,
                parent_folders=profile.get("parent_folders", None),
                is_review_list=profile.get("is_review_list", False),
            )
        )

    def _get_config_from_profile(
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
