"""Collect launch-context data for published workfile copy flow."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.hooks.pre_find_last_published_workfile_representation import FindLastPublishedWorkfileRepresentation
from ayon_core.pipeline.workfile import get_workfile_on_launch_profile


class CollectLastPublishedWorkfileData(PreLaunchHook):
    """Collect settings and extension inputs for published workfile copy."""

    order = FindLastPublishedWorkfileRepresentation.order - 0.001
    launch_types = {LaunchTypes.local}

    def execute(self):
        if not self.data.get("start_last_workfile"):
            return

        project_name = self.data["project_name"]
        task_name = self.data["task_name"]
        task_type = self.data["task_type"]
        host_name = self.application.host_name

        profile = get_workfile_on_launch_profile(
            project_name,
            host_name,
            task_name,
            task_type,
            project_settings=self.data.get("project_settings"),
        )
        if not profile or not profile.get("use_last_published_workfile"):
            return

        folder_entity = self.data.get("folder_entity")
        task_entity = self.data.get("task_entity")
        if not folder_entity or not task_entity:
            return

        host_addon = self.addons_manager.get_host_addon(host_name)
        extensions = None
        if host_addon:
            extensions = host_addon.get_workfile_extensions()

        self.data["copy_last_published_workfile_enabled"] = True
        self.data["copy_last_published_workfile_extensions"] = extensions
