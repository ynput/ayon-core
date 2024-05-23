import ayon_api

from ayon_clockify.clockify_api import ClockifyAPI
from ayon_core.pipeline import LauncherAction


class ClockifyPermissionsCheckFailed(Exception):
    """Timer start failed due to user permissions check.
    Message should be self explanatory as traceback won't be shown.
    """

    pass


class ClockifySync(LauncherAction):
    name = "sync_to_clockify"
    label = "Sync to Clockify"
    icon = "app_icons/clockify-white.png"
    order = 500
    clockify_api = ClockifyAPI()

    def is_compatible(self, selection):
        """Check if there's some projects to sync"""
        if selection.is_project_selected:
            return True

        try:
            next(ayon_api.get_projects())
            return True
        except StopIteration:
            return False

    def process(self, selection, **kwargs):
        self.clockify_api.set_api()
        workspace_id = self.clockify_api.workspace_id
        user_id = self.clockify_api.user_id
        if not self.clockify_api.validate_workspace_permissions(
            workspace_id, user_id
        ):
            raise ClockifyPermissionsCheckFailed(
                "Current CLockify user is missing permissions for this action!"
            )

        if selection.is_project_selected:
            projects_to_sync = [selection.project_entity]
        else:
            projects_to_sync = ayon_api.get_projects()

        projects_info = {
            project["name"]: {
                task_type["name"]
                for task_type in project["taskTypes"]
            }
            for project in projects_to_sync
        }

        clockify_projects = self.clockify_api.get_projects(workspace_id)
        for project_name, task_types in projects_info.items():
            if project_name in clockify_projects:
                continue

            response = self.clockify_api.add_project(
                project_name, workspace_id
            )
            if "id" not in response:
                self.log.error(
                    "Project {} can't be created".format(project_name)
                )
                continue

            clockify_workspace_tags = self.clockify_api.get_tags(workspace_id)
            for task_type in task_types:
                if task_type not in clockify_workspace_tags:
                    response = self.clockify_api.add_tag(
                        task_type, workspace_id
                    )
                    if "id" not in response:
                        self.log.error(
                            "Task {} can't be created".format(task_type)
                        )
                        continue
