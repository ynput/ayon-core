"""Resolve latest published workfile representation for launch context."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.hooks.pre_copy_last_published_workfile import CopyLastPublishedWorkfile
from ayon_core.pipeline.workfile import get_last_published_workfile_representation


class FindLastPublishedWorkfileRepresentation(PreLaunchHook):
    """Find the latest published workfile representation for the context."""

    order = CopyLastPublishedWorkfile.order - 0.001
    launch_types = {LaunchTypes.local}

    def execute(self):
        if not self.data.get("copy_last_published_workfile_enabled"):
            return

        project_name = self.data["project_name"]
        folder_entity = self.data.get("folder_entity")
        task_entity = self.data.get("task_entity")
        if not folder_entity or not task_entity:
            return

        anatomy = self.data.get("anatomy")
        project_settings = self.data.get("project_settings")
        extensions = self.data.get("copy_last_published_workfile_extensions")

        published_info = get_last_published_workfile_representation(
            project_name,
            folder_entity["id"],
            task_entity["id"],
            extensions=extensions,
            anatomy=anatomy,
            project_settings=project_settings,
        )
        self.data["last_published_workfile_info"] = published_info
