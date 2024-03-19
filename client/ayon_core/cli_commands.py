# -*- coding: utf-8 -*-
"""Implementation of AYON commands."""
import os
import sys
import json
import warnings


class Commands:
    """Class implementing commands used by AYON.

    Most of its methods are called by :mod:`cli` module.
    """
    @staticmethod
    def launch_tray():
        from ayon_core.lib import Logger
        from ayon_core.tools import tray

        Logger.set_process_name("Tray")

        tray.main()

    @staticmethod
    def add_addons(click_func):
        """Modules/Addons can add their cli commands dynamically."""

        from ayon_core.lib import Logger
        from ayon_core.addon import AddonsManager

        manager = AddonsManager()
        log = Logger.get_logger("CLI-AddModules")
        for addon in manager.addons:
            try:
                addon.cli(click_func)

            except Exception:
                log.warning(
                    "Failed to add cli command for module \"{}\"".format(
                        addon.name
                    )
                )
        return click_func

    @staticmethod
    def publish(path: str, targets: list=None, gui:bool=False) -> None:
        """Start headless publishing.

        Publish use json from passed path argument.

        Args:
            path (str): Path to JSON.
            targets (list of str): List of pyblish targets.
            gui (bool): Show publish UI.

        Raises:
            RuntimeError: When there is no path to process.
            RuntimeError: When executed with list of JSON paths.

        """
        from ayon_core.lib import Logger
        from ayon_core.lib.applications import (
            get_app_environments_for_context,
            LaunchTypes,
        )
        from ayon_core.addon import AddonsManager
        from ayon_core.pipeline import (
            install_ayon_plugins,
            get_global_context,
        )
        from ayon_core.tools.utils.host_tools import show_publish
        from ayon_core.tools.utils.lib import qt_app_context

        # Register target and host
        import pyblish.api
        import pyblish.util

        if not isinstance(path, str):
            raise RuntimeError("Path to JSON must be a string.")

        # Fix older jobs
        for src_key, dst_key in (
            ("AVALON_PROJECT", "AYON_PROJECT_NAME"),
            ("AVALON_ASSET", "AYON_FOLDER_PATH"),
            ("AVALON_TASK", "AYON_TASK_NAME"),
            ("AVALON_WORKDIR", "AYON_WORKDIR"),
            ("AVALON_APP_NAME", "AYON_APP_NAME"),
            ("AVALON_APP", "AYON_HOST_NAME"),
        ):
            if src_key in os.environ and dst_key not in os.environ:
                os.environ[dst_key] = os.environ[src_key]
            # Remove old keys, so we're sure they're not used
            os.environ.pop(src_key, None)

        log = Logger.get_logger("CLI-publish")

        install_ayon_plugins()

        manager = AddonsManager()

        publish_paths = manager.collect_plugin_paths()["publish"]

        for plugin_path in publish_paths:
            pyblish.api.register_plugin_path(plugin_path)

        app_full_name = os.getenv("AYON_APP_NAME")
        if app_full_name:
            context = get_global_context()
            env = get_app_environments_for_context(
                context["project_name"],
                context["folder_path"],
                context["task_name"],
                app_full_name,
                launch_type=LaunchTypes.farm_publish,
            )
            os.environ.update(env)

        pyblish.api.register_host("shell")

        if targets:
            for target in targets:
                print(f"setting target: {target}")
                pyblish.api.register_target(target)
        else:
            pyblish.api.register_target("farm")

        os.environ["AYON_PUBLISH_DATA"] = path
        os.environ["HEADLESS_PUBLISH"] = 'true'  # to use in app lib

        log.info("Running publish ...")

        plugins = pyblish.api.discover()
        print("Using plugins:")
        for plugin in plugins:
            print(plugin)

        if gui:
            with qt_app_context():
                show_publish()
        else:
            # Error exit as soon as any error occurs.
            error_format = ("Failed {plugin.__name__}: "
                            "{error} -- {error.traceback}")

            for result in pyblish.util.publish_iter():
                if result["error"]:
                    log.error(error_format.format(**result))
                    # uninstall()
                    sys.exit(1)

        log.info("Publish finished.")

    @staticmethod
    def extractenvironments(output_json_path, project, folder, task, app,
                            env_group):
        """Produces json file with environment based on project and app.

        Called by Deadline plugin to propagate environment into render jobs.
        """

        from ayon_core.lib.applications import (
            get_app_environments_for_context,
            LaunchTypes,
        )

        if all((project, folder, task, app)):
            env = get_app_environments_for_context(
                project,
                folder,
                task,
                app,
                env_group=env_group,
                launch_type=LaunchTypes.farm_render
            )
        else:
            env = os.environ.copy()

        output_dir = os.path.dirname(output_json_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_json_path, "w") as file_stream:
            json.dump(env, file_stream, indent=4)

    @staticmethod
    def contextselection(output_path, project_name, folder_path, strict):
        from ayon_core.tools.context_dialog import main

        main(output_path, project_name, folder_path, strict)
