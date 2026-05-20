from typing import List

import pyblish.api
import ayon_api
from ayon_core.lib import EnumDef, filter_profiles
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_core.pipeline import get_current_project_name


class IntegrateStatus(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Allow user to set status for the published version
    based on profiles defined in settings."""

    order = pyblish.api.IntegratorOrder - 0.01
    label = "Integrate Status"

    status_profiles: List[dict] = []

    def process(self, instance):
        if not self.status_profiles:
            self.log.debug("No status profiles defined in settings.")
            return

        version_data = instance.data.setdefault("versionData", {})
        if "status" in version_data:
            # already set so we won't override it
            return
        folder_entity = instance.data["folderEntity"]
        task_entity = instance.data["taskEntity"]
        filter_data = {
            "host_names": instance.context.data["hostName"],
            "task_types": task_entity["taskType"],
            "task_names": task_entity["name"],
            "folder_paths": folder_entity["path"]
        }
        status_profile = filter_profiles(
            self.status_profiles,
            filter_data,
            logger=self.log
        )
        if status_profile is None:
            self.log.debug("No matching status profile found.")
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        status = attr_values.get("status")
        instance.data["status"] = status

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: "CreateContext", instance: "CreatedInstance"
    ):
        if not cls.status_profiles:
            return []
        project_entity = context.get_current_project_entity()
        statuses = [
            status["name"]
            for status in project_entity["statuses"]
        ]

        return [
            EnumDef(
                "status",
                label="Set status",
                items=statuses,
                default=statuses[0]
            )
        ]
