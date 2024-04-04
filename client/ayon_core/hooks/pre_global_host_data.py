from ayon_api import get_project, get_folder_by_path, get_task_by_name

from ayon_applications import PreLaunchHook
from ayon_applications.utils import (
    EnvironmentPrepData,
    prepare_app_environments,
    prepare_context_environments
)
from ayon_core.pipeline import Anatomy


class GlobalHostDataHook(PreLaunchHook):
    order = -100
    launch_types = set()

    def execute(self):
        """Prepare global objects to `data` that will be used for sure."""
        self.prepare_global_data()

        if not self.data.get("folder_entity"):
            return

        app = self.launch_context.application
        temp_data = EnvironmentPrepData({
            "project_name": self.data["project_name"],
            "folder_path": self.data["folder_path"],
            "task_name": self.data["task_name"],

            "app": app,

            "project_entity": self.data["project_entity"],
            "folder_entity": self.data["folder_entity"],
            "task_entity": self.data["task_entity"],

            "anatomy": self.data["anatomy"],

            "env": self.launch_context.env,

            "start_last_workfile": self.data.get("start_last_workfile"),
            "last_workfile_path": self.data.get("last_workfile_path"),

            "log": self.log
        })

        prepare_app_environments(temp_data, self.launch_context.env_group)
        prepare_context_environments(temp_data)

        temp_data.pop("log")

        self.data.update(temp_data)

    def prepare_global_data(self):
        """Prepare global objects to `data` that will be used for sure."""
        # Mongo documents
        project_name = self.data.get("project_name")
        if not project_name:
            self.log.info(
                "Skipping global data preparation."
                " Key `project_name` was not found in launch context."
            )
            return

        self.log.debug("Project name is set to \"{}\"".format(project_name))

        # Project Entity
        project_entity = get_project(project_name)
        self.data["project_entity"] = project_entity

        # Anatomy
        self.data["anatomy"] = Anatomy(
            project_name, project_entity=project_entity
        )

        folder_path = self.data.get("folder_path")
        if not folder_path:
            self.log.warning(
                "Folder path is not set. Skipping folder query."
            )
            return

        folder_entity = get_folder_by_path(project_name, folder_path)
        self.data["folder_entity"] = folder_entity

        task_name = self.data.get("task_name")
        if not task_name:
            self.log.warning(
                "Task name is not set. Skipping task query."
            )
            return

        if not folder_entity:
            return

        task_entity = get_task_by_name(
            project_name, folder_entity["id"], task_name
        )
        self.data["task_entity"] = task_entity