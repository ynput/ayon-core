"""Collect reviewers for published versions.

Options are resolved from the project users. The collected names are put
into ``instance.data['assignees']`` and written onto the task entity by
:mod:`integrate_assignees`, because ``assignees`` is a task level field
in AYON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyblish.api
import ayon_api
from ayon_core.lib import (
    EnumDef,
    TextDef,
    AYONUrlIcon,
    filter_profiles,
)

from ayon_core.pipeline.publish import AYONPyblishPluginMixin

if TYPE_CHECKING:
    from ayon_core.pipeline.create import (
        CreateContext,
        CreatedInstance,
    )


class CollectAssignees(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Allow to define reviewers for the task of published versions.

    Reviewer options are resolved from the project users. Settings can
    preselect reviewers and lock the selection so the artist cannot
    change them.
    """

    order = pyblish.api.CollectorOrder + 0.499
    label = "Collect Assignees"

    enabled = False
    assignee_profiles: list[dict] = []

    # Cache of project user items by project name
    _user_items_cache: dict[str, list[dict]] = {}

    def process(self, instance: pyblish.api.Instance) -> None:
        if not self.assignee_profiles:
            return

        if not instance.data.get("taskEntity"):
            self.log.warning(
                "Instance '{}' has assignees but no task, skipping."
                .format(instance.data.get("name") or instance.name)
            )
            return

        if instance.data.get("assignees"):
            # already set so we won't override it
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        assignees_state = attr_values.get("assignees_state")
        if not assignees_state or assignees_state == "dont_use":
            return

        if assignees_state == "use_assignees":
            assignees = attr_values.get("assignees") or []
        elif assignees_state.startswith("assignees|"):
            names = assignees_state.removeprefix("assignees|").split(",")
            assignees = [name for name in names if name]
        else:
            return

        if not assignees:
            return

        # 'IntegrateAssignees' writes these onto the task entity,
        # 'assignees' is a task level field in AYON.
        instance.data["assignees"] = list(assignees)

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: "CreateContext", instance: "CreatedInstance"
    ):
        assignees_state_attr = TextDef(
            "assignees_state", visible=False, default="dont_use"
        )
        output = [assignees_state_attr]
        if not cls.assignee_profiles:
            cls._set_instance_state(instance, "dont_use")
            return output

        project_name = create_context.get_current_project_name()
        assignees_items = cls._get_user_items(project_name)
        if not assignees_items:
            cls.log.warning("No project users found to assign.")
            cls._set_instance_state(instance, "dont_use")
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

        assignees_profile = filter_profiles(
            cls.assignee_profiles,
            filter_data,
            logger=cls.log
        )
        default_assignees = []
        artist_can_change = True
        if assignees_profile:
            artist_can_change = assignees_profile["artist_can_change"]
            default_assignees = assignees_profile["default_assignees"] or []

        unavailable = [
            name for name in default_assignees if name not in default_assignees
        ]
        if unavailable:
            cls.log.warning(
                "Default assignees are not available on project"
                f" '{project_name}': {unavailable}"
            )
            default_assignees = [
                name for name in default_assignees if name in default_assignees
            ]

        if not artist_can_change:
            cls._set_instance_state(
                instance,
                f"assignees|{','.join(default_assignees)}"
            )
            cls.log.debug(
                "Artist cannot change assignees based on profile settings."
            )
            return output

        cls._set_instance_state(instance, "use_assignees")

        output.append(EnumDef(
            "assignees",
            label="Assignees",
            items=assignees_items,
            default=default_assignees,
            multiselection=True,
        ))
        return output

    @classmethod
    def _get_user_items(cls, project_name: str) -> list[dict]:
        """Return items for users available in a project.

        The result is cached by project name, users are queried once
        per publish session.

        Args:
            project_name (str): Name of the project.

        Returns:
            list[dict]: Enum items for the project users.
        """
        if project_name not in cls._user_items_cache:
            items: list[dict] = []
            for user in ayon_api.get_users(project_name=project_name):
                user_name = user["name"]
                items.append({
                    "value": user_name,
                    "label": (
                        user.get("attrib", {}).get("fullName") or user_name
                    ),
                    "icon": AYONUrlIcon(f"users/{user_name}/avatar"),
                })
            cls._user_items_cache[project_name] = items
        return cls._user_items_cache[project_name]

    @classmethod
    def _set_instance_state(
        cls,
        instance: "CreatedInstance",
        state: str
    ) -> None:
        plugin_attributes = instance.publish_attributes.get(cls.__name__)
        if plugin_attributes is None:
            return

        plugin_attributes["assignees_state"] = state
