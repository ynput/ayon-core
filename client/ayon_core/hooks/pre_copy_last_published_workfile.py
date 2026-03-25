"""Copy last published workfile into local work directory."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.hooks.pre_add_last_workfile_arg import AddLastWorkfileToLaunchArgs
from ayon_core.pipeline.workfile import copy_last_published_workfile


class CopyLastPublishedWorkfile(PreLaunchHook):
    """Copy the found published workfile and update launch context paths."""

    order = AddLastWorkfileToLaunchArgs.order - 0.001
    launch_types = {LaunchTypes.local}

    def execute(self):
        if not self.data.get("copy_last_published_workfile_enabled"):
            return

        published_info = self.data.get("last_published_workfile_info")
        if not published_info:
            return

        project_name = self.data["project_name"]
        host_name = self.application.host_name
        folder_entity = self.data["folder_entity"]
        task_entity = self.data["task_entity"]
        anatomy = self.data.get("anatomy")
        project_settings = self.data.get("project_settings")

        new_path = copy_last_published_workfile(
            project_name,
            folder_entity,
            task_entity,
            host_name,
            published_info,
            workdir=None,
            file_template=None,
            workdir_data=None,
            anatomy=anatomy,
            project_settings=project_settings,
            log=self.log,
        )
        if new_path:
            self.data["last_workfile_path"] = new_path
            self.data["env"]["AYON_LAST_WORKFILE"] = new_path
