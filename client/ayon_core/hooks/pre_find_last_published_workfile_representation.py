"""Resolve latest published workfile representation for launch context."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.pipeline.workfile import (
    get_last_published_workfile_representation,
)


class FindLastPublishedWorkfileRepresentation(PreLaunchHook):
    """Find the latest published workfile representation for the context."""

    order = 5 - 0.1  # Before CopyLastPublishedWorkfile
    launch_types = {LaunchTypes.local}

    def execute(self):
        if not self.data.get("copy_last_published_workfile_enabled"):
            return

        project_name = self.data["project_name"]
        folder_entity = self.data.get("folder_entity")
        task_entity = self.data.get("task_entity")

        host_addon = self.addons_manager.get_host_addon(
            self.application.host_name
        )
        extensions = {
            str(ext).lstrip(".").lower()
            for ext in host_addon.get_workfile_extensions()
        }

        anatomy = self.data.get("anatomy")
        project_settings = self.data.get("project_settings")
        self.data["last_published_workfile_info"] = (
            get_last_published_workfile_representation(
                project_name,
                folder_entity["id"],
                task_entity["id"],
                extensions=extensions,
                anatomy=anatomy,
                project_settings=project_settings,
            )
        )
