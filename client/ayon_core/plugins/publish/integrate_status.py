from __future__ import annotations
from typing import TYPE_CHECKING

import pyblish.api
from ayon_core.lib import EnumDef, filter_profiles
from ayon_core.pipeline.publish import AYONPyblishPluginMixin

if TYPE_CHECKING:
    from ayon_core.create_context import CreateContext
    from ayon_core.created_instance import CreatedInstance


class IntegrateStatus(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Allow user to set status for the published version
    based on profiles defined in settings."""

    order = pyblish.api.IntegratorOrder - 0.01
    label = "Integrate Status"

    status_profiles: list[dict] = []

    def process(self, instance):
        if not self.status_profiles:
            return

        if instance.data.get("status"):
            # already set so we won't override it
            return
        attr_values = self.get_attr_values_from_data(instance.data)
        status = attr_values.get("status")
        if status:
            instance.data["status"] = status

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: "CreateContext", instance: "CreatedInstance"
    ):
        if not cls.status_profiles:
            return []
        project_entity = create_context.get_current_project_entity()
        statuses = [
            status["name"]
            for status in project_entity["statuses"]
            if "version" in status["scope"]
        ]
        if not statuses:
            cls.log.warning("No version statuses found in current project.")
            return []
        folder_path = instance.get("folderPath")
        folder_entity = create_context.get_folder_entity(folder_path)
        task_entity = None
        if folder_entity:
            task_name = instance.get("task")
            task_entity = create_context.get_task_entity(
                folder_path, task_name
            )
        filter_data = {
            "host_names": create_context.host_name,
            "task_types": task_entity["taskType"],
            "task_names": instance.get("task"),
            "product_base_types": instance.product_base_type,
        }
        if task_entity:
            filter_data["task_types"] = task_entity["taskType"]

        status_profile = filter_profiles(
            cls.status_profiles,
            filter_data,
            logger=cls.log
        )
        default_status = None
        showed_in_publisher_ui = True
        if status_profile:
            showed_in_publisher_ui = status_profile.get(
                "show_in_publisher_ui", True
            )
            default_status = status_profile["default_status"]

        if default_status not in statuses:
            cls.log.warning(
                f"Default status '{default_status}' is not available"
                f" on project: {project_entity['name']}"
                f"Use {statuses[0]} instead."
            )
            default_status = statuses[0]
        return [
            EnumDef(
                "status",
                label="Version status",
                items=statuses,
                visible=showed_in_publisher_ui,
                default=default_status,
            )
        ]
