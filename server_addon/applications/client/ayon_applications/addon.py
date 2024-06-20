import os
import json

import ayon_api

from ayon_core.addon import AYONAddon, IPluginPaths, click_wrap

from .version import __version__
from .constants import APPLICATIONS_ADDON_ROOT
from .defs import LaunchTypes
from .manager import ApplicationManager


class ApplicationsAddon(AYONAddon, IPluginPaths):
    name = "applications"
    version = __version__

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

    def get_app_icon_path(self, icon_filename):
        """Get icon path.

        Args:
            icon_filename (str): Icon filename.

        Returns:
            Union[str, None]: Icon path or None if not found.

        """
        if not icon_filename:
            return None
        icon_name = os.path.basename(icon_filename)
        path = os.path.join(APPLICATIONS_ADDON_ROOT, "icons", icon_name)
        if os.path.exists(path):
            return path
        return None

    def get_app_icon_url(self, icon_filename, server=False):
        """Get icon path.

        Method does not validate if icon filename exist on server.

        Args:
            icon_filename (str): Icon name.
            server (Optional[bool]): Return url to AYON server.

        Returns:
            Union[str, None]: Icon path or None is server url is not
                available.

        """
        if not icon_filename:
            return None
        icon_name = os.path.basename(icon_filename)
        if server:
            base_url = ayon_api.get_base_url()
            return (
                f"{base_url}/addons/{self.name}/{self.version}"
                f"/public/icons/{icon_name}"
            )
        server_url = os.getenv("AYON_WEBSERVER_URL")
        if not server_url:
            return None
        return "/".join([
            server_url, "addons", self.name, self.version, "icons", icon_name
        ])

    def get_applications_action_classes(self):
        """Get application action classes for launcher tool.

        This method should be used only by launcher tool. Please do not use it
        in other places as its implementation is not optimal, and might
        change or be removed.

        Returns:
            list[ApplicationAction]: List of application action classes.

        """
        from .action import ApplicationAction

        actions = []

        manager = self.get_applications_manager()
        for full_name, application in manager.applications.items():
            if not application.enabled:
                continue

            icon = self.get_app_icon_path(application.icon)

            action = type(
                "app_{}".format(full_name),
                (ApplicationAction,),
                {
                    "identifier": "application.{}".format(full_name),
                    "application": application,
                    "name": application.name,
                    "label": application.group.label,
                    "label_variant": application.label,
                    "group": None,
                    "icon": icon,
                    "color": getattr(application, "color", None),
                    "order": getattr(application, "order", None) or 0,
                    "data": {}
                }
            )
            actions.append(action)
        return actions

    def launch_application(
        self, app_name, project_name, folder_path, task_name
    ):
        """Launch application.

        Args:
            app_name (str): Full application name e.g. 'maya/2024'.
            project_name (str): Project name.
            folder_path (str): Folder path.
            task_name (str): Task name.

        """
        app_manager = self.get_applications_manager()
        return app_manager.launch(
            app_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
        )

    def webserver_initialization(self, manager):
        """Initialize webserver.

        Args:
            manager (WebServerManager): Webserver manager.

        """
        static_prefix = f"/addons/{self.name}/{self.version}/icons"
        manager.add_static(
            static_prefix, os.path.join(APPLICATIONS_ADDON_ROOT, "icons")
        )

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
        (
            main_group.command(
                self._cli_launch_applications,
                name="launch",
                help="Launch application"
            )
            .option("--app", required=True, help="Application name")
            .option("--project", required=True, help="Project name")
            .option("--folder", required=True, help="Folder path")
            .option("--task", required=True, help="Task name")
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

    def _cli_launch_applications(self, project, folder, task, app):
        """Launch application.

        Args:
            project (str): Project name.
            folder (str): Folder path.
            task (str): Task name.
            app (str): Full application name e.g. 'maya/2024'.

        """
        self.launch_application(app, project, folder, task)
