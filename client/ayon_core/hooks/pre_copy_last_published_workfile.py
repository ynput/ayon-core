"""Pre-launch hook to copy the last published workfile into the work directory."""

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.hooks.pre_add_last_workfile_arg import AddLastWorkfileToLaunchArgs
from ayon_core.pipeline.workfile import (
    get_workfile_on_launch_profile,
    get_last_published_workfile_representation,
    copy_last_published_workfile,
)


class CopyLastPublishedWorkfile(PreLaunchHook):
    """Copy the last published workfile to the work directory.

    Runs before the workfile path is added to launch args. 
    Reads the 'use_last_published_workfile' flag from the matched
    last_workfile_on_startup profile. Only copies when the published
    file is newer than the latest local workfile.
    """

    order = AddLastWorkfileToLaunchArgs.order - 0.001
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

        anatomy = self.data.get("anatomy")
        project_settings = self.data.get("project_settings")

        published_info = get_last_published_workfile_representation(
            project_name,
            folder_entity["id"],
            task_entity["id"],
            extensions=extensions,
            anatomy=anatomy,
            project_settings=project_settings,
        )
        if not published_info:
            return

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
