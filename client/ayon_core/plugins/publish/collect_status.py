from __future__ import annotations
from typing import TYPE_CHECKING

import pyblish.api
from ayon_core.lib import EnumDef, TextDef, filter_profiles
from ayon_core.pipeline.publish import AYONPyblishPluginMixin

if TYPE_CHECKING:
    from ayon_core.pipeline.create import (
        CreateContext,
        CreatedInstance,
    )


class CollectStatus(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Allow user to set status for the published version
    based on profiles defined in settings."""

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Status"

    enabled = False
    status_profiles: list[dict] = []

    def process(self, instance):
        if not self.status_profiles:
            return

        if instance.data.get("status"):
            # already set so we won't override it
            return
        attr_values = self.get_attr_values_from_data(instance.data)
        status_state = attr_values.get("status_state")
        if status_state == "dont_use":
            return

        if status_state == "use_status":
            status = attr_values.get("status", "")
        elif status_state.startswith("use|"):
            status = status_state.split("|", 1)[1]
        else:
            return
        if status:
            instance.data["status"] = status

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: "CreateContext", instance: "CreatedInstance"
    ):
        status_state_attr = TextDef(
            "status_state", visible=False, default="dont_use"
        )
        output = [status_state_attr]
        if not cls.status_profiles:
            cls._set_instance_state(instance, status_state_attr, "dont_use")
            return output

        project_entity = create_context.get_current_project_entity()
        statuses = [
            status["name"]
            for status in project_entity["statuses"]
            if "version" in status["scope"]
        ]
        if not statuses:
            cls.log.warning("No version statuses found in current project.")
            cls._set_instance_state(instance, status_state_attr, "dont_use")
            return output

        folder_path = instance.get("folderPath")
        folder_entity = create_context.get_folder_entity(folder_path)
        task_entity = None
        task_name = None
        task_type = None
        if folder_entity:
            task_name = instance.get("task")
            task_entity = create_context.get_task_entity(
                folder_path, task_name
            )
            if task_entity:
                task_type = task_entity["taskType"]

        filter_data = {
            "host_names": create_context.host_name,
            "task_types": task_type,
            "task_names": task_name,
            "product_base_types": instance.product_base_type,
        }

        status_profile = filter_profiles(
            cls.status_profiles,
            filter_data,
            logger=cls.log
        )
        default_status = None
        artist_can_change = True
        if status_profile:
            artist_can_change = status_profile.get(
                "artist_can_change", True
            )
            default_status = status_profile.get("default_status", "")
            if not artist_can_change:
                cls._set_instance_state(
                    instance, status_state_attr, f"status|{default_status}"
                )
                cls.log.debug(
                    "Artist cannot change status based on profile settings."
                )
                return output

            default_status = status_profile["default_status"]

        cls._set_instance_state(instance, status_state_attr, "use_status")
        if default_status not in statuses:
            cls.log.warning(
                f"Default status '{default_status}' is not available"
                f" on project: {project_entity['name']}"
                f"Using '{statuses[0]}' instead."
            )
            default_status = statuses[0]
        output.append(EnumDef(
           "status",
            label="Version status",
            items=statuses,
            default=default_status,
        ))
        return output

    @classmethod
    def _set_instance_state(
        cls,
        instance: "CreatedInstance",
        status_state_attr: "TextDef",
        state: str
    ) -> None:
        status_state_attr.default = state
        plugin_attributes = instance.publish_attributes.get(cls.__name__)
        if plugin_attributes is None:
            return

        plugin_attributes["status_state"] = state
        cls._set_instance_state(instance, status_state_attr, "dont_use")
