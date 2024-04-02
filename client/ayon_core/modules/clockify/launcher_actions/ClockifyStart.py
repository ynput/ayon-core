import ayon_api

from ayon_core.pipeline import LauncherAction
from openpype_modules.clockify.clockify_api import ClockifyAPI


class ClockifyStart(LauncherAction):
    name = "clockify_start_timer"
    label = "Clockify - Start Timer"
    icon = "app_icons/clockify.png"
    order = 500
    clockify_api = ClockifyAPI()

    def is_compatible(self, selection):
        """Return whether the action is compatible with the session"""
        return selection.is_task_selected

    def process(self, selection, **kwargs):
        self.clockify_api.set_api()
        user_id = self.clockify_api.user_id
        workspace_id = self.clockify_api.workspace_id
        project_name = selection.project_name
        folder_path = selection.folder_path
        task_name = selection.task_name
        description = "/".join([folder_path.lstrip("/"), task_name])

        # fetch folder entity
        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name
        )

        # get task type to fill the timer tag
        task_type = task_entity["taskType"]

        project_id = self.clockify_api.get_project_id(
            project_name, workspace_id
        )
        tag_ids = []
        tag_name = task_type
        tag_ids.append(self.clockify_api.get_tag_id(tag_name, workspace_id))
        self.clockify_api.start_time_entry(
            description,
            project_id,
            tag_ids=tag_ids,
            workspace_id=workspace_id,
            user_id=user_id,
        )
