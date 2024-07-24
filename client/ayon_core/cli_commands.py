# -*- coding: utf-8 -*-
"""Implementation of AYON commands."""
import os
import sys
import warnings
from typing import Optional, List

from ayon_core.addon import AddonsManager


class Commands:
    """Class implementing commands used by AYON.

    Most of its methods are called by :mod:`cli` module.
    """
    @staticmethod
    def publish(
        path: str,
        targets: Optional[List[str]] = None,
        gui: Optional[bool] = False,
        addons_manager: Optional[AddonsManager] = None,
    ) -> None:
        """Start headless publishing.

        Publish use json from passed path argument.

        Args:
            path (str): Path to JSON.
            targets (Optional[List[str]]): List of pyblish targets.
            gui (Optional[bool]): Show publish UI.
            addons_manager (Optional[AddonsManager]): Addons manager instance.

        Raises:
            RuntimeError: When there is no path to process.
            RuntimeError: When executed with list of JSON paths.

        """
        from ayon_core.lib import Logger

        from ayon_core.addon import AddonsManager
        from ayon_core.pipeline import (
            install_ayon_plugins,
            get_global_context,
        )

        import ayon_api
        import pyblish.util

        # Register target and host
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

        # Make public ayon api behave as other user
        # - this works only if public ayon api is using service user
        username = os.environ.get("AYON_USERNAME")
        if username:
            # NOTE: ayon-python-api does not have public api function to find
            #   out if is used service user. So we need to have try > except
            #   block.
            con = ayon_api.get_server_api_connection()
            try:
                con.set_default_service_username(username)
            except ValueError:
                pass

        install_ayon_plugins()

        if addons_manager is None:
            addons_manager = AddonsManager()

        publish_paths = addons_manager.collect_plugin_paths()["publish"]

        for plugin_path in publish_paths:
            pyblish.api.register_plugin_path(plugin_path)

        applications_addon = addons_manager.get_enabled_addon("applications")
        if applications_addon is not None:
            context = get_global_context()
            env = applications_addon.get_farm_publish_environment_variables(
                context["project_name"],
                context["folder_path"],
                context["task_name"],
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
            from ayon_core.tools.utils.host_tools import show_publish
            from ayon_core.tools.utils.lib import qt_app_context
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
    def extractenvironments(
        output_json_path, project, asset, task, app, env_group, addons_manager
    ):
        """Produces json file with environment based on project and app.

        Called by Deadline plugin to propagate environment into render jobs.
        """
        warnings.warn(
            (
                "Command 'extractenvironments' is deprecated and will be"
                " removed in future. Please use "
                "'addon applications extractenvironments ...' instead."
            ),
            DeprecationWarning
        )

        applications_addon = addons_manager.get_enabled_addon("applications")
        if applications_addon is None:
            raise RuntimeError(
                "Applications addon is not available or enabled."
            )

        # Please ignore the fact this is using private method
        applications_addon._cli_extract_environments(
            output_json_path, project, asset, task, app, env_group
        )

    @staticmethod
    def contextselection(output_path, project_name, folder_path, strict):
        from ayon_core.tools.context_dialog import main

        main(output_path, project_name, folder_path, strict)
