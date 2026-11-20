"""Collect launch-context data for published workfile copy flow."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.pipeline.workfile import get_workfile_on_launch_profile


class CollectLastPublishedWorkfileData(PreLaunchHook):
    """Collect settings and extension inputs for published workfile copy."""

    order = 5 - 0.2  # Before FindLastPublishedWorkfileRepresentation
    launch_types = {LaunchTypes.local}

    def execute(self):
        if self.data.get("workfile_path") or not self.data.get(
            "start_last_workfile"
        ):
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
        if not profile or not profile.use_last_published_workfile:
            return

        self.data["copy_last_published_workfile_enabled"] = True
