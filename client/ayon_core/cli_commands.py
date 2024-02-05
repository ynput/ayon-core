# -*- coding: utf-8 -*-
"""Implementation of Pype commands."""
import os
import sys
import json


class Commands:
    """Class implementing commands used by Pype.

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
        from ayon_core.modules import ModulesManager

        manager = ModulesManager()
        log = Logger.get_logger("CLI-AddModules")
        for addon in manager.modules:
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
    def publish(paths, targets=None, gui=False):
        """Start headless publishing.

        Publish use json from passed paths argument.

        Args:
            paths (list): Paths to jsons.
            targets (string): What module should be targeted
                (to choose validator for example)
            gui (bool): Show publish UI.

        Raises:
            RuntimeError: When there is no path to process.
        """

        from ayon_core.lib import Logger
        from ayon_core.lib.applications import (
            get_app_environments_for_context,
            LaunchTypes,
        )
        from ayon_core.modules import ModulesManager
        from ayon_core.pipeline import (
            install_openpype_plugins,
            get_global_context,
        )
        from ayon_core.tools.utils.host_tools import show_publish
        from ayon_core.tools.utils.lib import qt_app_context

        # Register target and host
        import pyblish.api
        import pyblish.util

        log = Logger.get_logger("CLI-publish")

        install_openpype_plugins()

        manager = ModulesManager()

        publish_paths = manager.collect_plugin_paths()["publish"]

        for path in publish_paths:
            pyblish.api.register_plugin_path(path)

        if not any(paths):
            raise RuntimeError("No publish paths specified")

        app_full_name = os.getenv("AVALON_APP_NAME")
        if app_full_name:
            context = get_global_context()
            env = get_app_environments_for_context(
                context["project_name"],
                context["asset_name"],
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

        os.environ["OPENPYPE_PUBLISH_DATA"] = os.pathsep.join(paths)
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
    def extractenvironments(output_json_path, project, asset, task, app,
                            env_group):
        """Produces json file with environment based on project and app.

        Called by Deadline plugin to propagate environment into render jobs.
        """

        from ayon_core.lib.applications import (
            get_app_environments_for_context,
            LaunchTypes,
        )

        if all((project, asset, task, app)):
            env = get_app_environments_for_context(
                project,
                asset,
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
    def contextselection(output_path, project_name, asset_name, strict):
        from ayon_core.tools.context_dialog import main

        main(output_path, project_name, asset_name, strict)

    @staticmethod
    def run_tests(folder, mark, pyargs,
                  test_data_folder, persist, app_variant, timeout, setup_only,
                  mongo_url, app_group, dump_databases):
        """
            Runs tests from 'folder'

            Args:
                 folder (str): relative path to folder with tests
                 mark (str): label to run tests marked by it (slow etc)
                 pyargs (str): package path to test
                 test_data_folder (str): url to unzipped folder of test data
                 persist (bool): True if keep test db and published after test
                    end
                app_variant (str): variant (eg 2020 for AE), empty if use
                    latest installed version
                timeout (int): explicit timeout for single test
                setup_only (bool): if only preparation steps should be
                    triggered, no tests (useful for debugging/development)
                mongo_url (str): url to Openpype Mongo database
        """
        print("run_tests")
        if folder:
            folder = " ".join(list(folder))
        else:
            folder = "../tests"

        # disable warnings and show captured stdout even if success
        args = [
            "--disable-pytest-warnings",
            "--capture=sys",
            "--print",
            "-W ignore::DeprecationWarning",
            "-rP",
            folder
        ]

        if mark:
            args.extend(["-m", mark])

        if pyargs:
            args.extend(["--pyargs", pyargs])

        if test_data_folder:
            args.extend(["--test_data_folder", test_data_folder])

        if persist:
            args.extend(["--persist", persist])

        if app_group:
            args.extend(["--app_group", app_group])

        if app_variant:
            args.extend(["--app_variant", app_variant])

        if timeout:
            args.extend(["--timeout", timeout])

        if setup_only:
            args.extend(["--setup_only", setup_only])

        if mongo_url:
            args.extend(["--mongo_url", mongo_url])

        if dump_databases:
            msg = "dump_databases format is not recognized: {}".format(
                dump_databases
            )
            assert dump_databases in ["bson", "json"], msg
            args.extend(["--dump_databases", dump_databases])

        print("run_tests args: {}".format(args))
        import pytest
        pytest.main(args)
