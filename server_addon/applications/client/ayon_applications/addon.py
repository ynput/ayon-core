import os
import json

from ayon_core.addon import AYONAddon, IPluginPaths, click_wrap

from .constants import APPLICATIONS_ADDON_ROOT
from .defs import LaunchTypes
from .manager import ApplicationManager


class ApplicationsAddon(AYONAddon, IPluginPaths):
    name = "applications"

    def initialize(self, settings):
        # TODO remove when addon is removed from ayon-core
        self.enabled = self.name in settings

    def get_app_environments_for_context(
        self,
        project_name,
        folder_path,
        task_name,
        full_app_name,
        env_group=None,
        launch_type=None,
        env=None,
    ):
        """Calculate environment variables for launch context.

        Args:
            project_name (str): Project name.
            folder_path (str): Folder path.
            task_name (str): Task name.
            full_app_name (str): Full application name.
            env_group (Optional[str]): Environment group.
            launch_type (Optional[str]): Launch type.
            env (Optional[dict[str, str]]): Environment variables to update.

        Returns:
            dict[str, str]: Environment variables for context.

        """
        from ayon_applications.utils import get_app_environments_for_context

        if not full_app_name:
            return {}

        return get_app_environments_for_context(
            project_name,
            folder_path,
            task_name,
            full_app_name,
            env_group=env_group,
            launch_type=launch_type,
            env=env,
            addons_manager=self.manager
        )

    def get_farm_publish_environment_variables(
        self,
        project_name,
        folder_path,
        task_name,
        full_app_name=None,
        env_group=None,
    ):
        """Calculate environment variables for farm publish.

        Args:
            project_name (str): Project name.
            folder_path (str): Folder path.
            task_name (str): Task name.
            env_group (Optional[str]): Environment group.
            full_app_name (Optional[str]): Full application name. Value from
                environment variable 'AYON_APP_NAME' is used if 'None' is
                passed.

        Returns:
            dict[str, str]: Environment variables for farm publish.

        """
        if full_app_name is None:
            full_app_name = os.getenv("AYON_APP_NAME")

        return self.get_app_environments_for_context(
            project_name,
            folder_path,
            task_name,
            full_app_name,
            env_group=env_group,
            launch_type=LaunchTypes.farm_publish
        )

    def get_applications_manager(self, settings=None):
        """Get applications manager.

        Args:
            settings (Optional[dict]): Studio/project settings.

        Returns:
            ApplicationManager: Applications manager.

        """
        return ApplicationManager(settings)

    def get_plugin_paths(self):
        return {
            "publish": [
                os.path.join(APPLICATIONS_ADDON_ROOT, "plugins", "publish")
            ]
        }

    # --- CLI ---
    def cli(self, addon_click_group):
        main_group = click_wrap.group(
            self._cli_main, name=self.name, help="Applications addon"
        )
        (
            main_group.command(
                self._cli_extract_environments,
                name="extractenvironments",
                help=(
                    "Extract environment variables for context into json file"
                )
            )
            .argument("output_json_path")
            .option("--project", help="Project name", default=None)
            .option("--folder", help="Folder path", default=None)
            .option("--task", help="Task name", default=None)
            .option("--app", help="Application name", default=None)
            .option(
                "--envgroup",
                help="Environment group (e.g. \"farm\")",
                default=None
            )
        )
        # Convert main command to click object and add it to parent group
        addon_click_group.add_command(
            main_group.to_click_obj()
        )

    def _cli_main(self):
        pass

    def _cli_extract_environments(
        self, output_json_path, project, folder, task, app, envgroup
    ):
        """Produces json file with environment based on project and app.

        Called by farm integration to propagate environment into farm jobs.

        Args:
            output_json_path (str): Output json file path.
            project (str): Project name.
            folder (str): Folder path.
            task (str): Task name.
            app (str): Full application name e.g. 'maya/2024'.
            envgroup (str): Environment group.

        """
        if all((project, folder, task, app)):
            env = self.get_farm_publish_environment_variables(
                project, folder, task, app, env_group=envgroup,
            )
        else:
            env = os.environ.copy()

        output_dir = os.path.dirname(output_json_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_json_path, "w") as file_stream:
            json.dump(env, file_stream, indent=4)
