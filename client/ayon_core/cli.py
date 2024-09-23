# -*- coding: utf-8 -*-
"""Package for handling AYON command line arguments."""
import os
import sys
import code
import traceback
from pathlib import Path
import warnings

import click
import acre

from ayon_core import AYON_CORE_ROOT
from ayon_core.addon import AddonsManager
from ayon_core.settings import get_general_environments
from ayon_core.lib import (
    initialize_ayon_connection,
    is_running_from_build,
    Logger,
)



@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--use-staging", is_flag=True,
              expose_value=False, help="use staging variants")
@click.option("--debug", is_flag=True, expose_value=False,
              help="Enable debug")
@click.option("--verbose", expose_value=False,
              help=("Change AYON log level (debug - critical or 0-50)"))
@click.option("--force", is_flag=True, hidden=True)
def main_cli(ctx, force):
    """AYON is main command serving as entry point to pipeline system.

    It wraps different commands together.
    """

    if ctx.invoked_subcommand is None:
        # Print help if headless mode is used
        if os.getenv("AYON_HEADLESS_MODE") == "1":
            print(ctx.get_help())
            sys.exit(0)
        else:
            ctx.forward(tray)


@main_cli.command()
@click.option(
    "--force",
    is_flag=True,
    help="Force to start tray and close any existing one.")
def tray(force):
    """Launch AYON tray.

    Default action of AYON command is to launch tray widget to control basic
    aspects of AYON. See documentation for more information.
    """

    from ayon_core.tools.tray import main

    main(force)


@main_cli.group(help="Run command line arguments of AYON addons")
@click.pass_context
def addon(ctx):
    """Addon specific commands created dynamically.

    These commands are generated dynamically by currently loaded addons.
    """
    pass


@main_cli.command()
@click.pass_context
@click.argument("output_json_path")
@click.option("--project", help="Project name", default=None)
@click.option("--asset", help="Folder path", default=None)
@click.option("--task", help="Task name", default=None)
@click.option("--app", help="Application name", default=None)
@click.option(
    "--envgroup", help="Environment group (e.g. \"farm\")", default=None
)
def extractenvironments(
    ctx, output_json_path, project, asset, task, app, envgroup
):
    """Extract environment variables for entered context to a json file.

    Entered output filepath will be created if does not exists.

    All context options must be passed otherwise only AYON's global
    environments will be extracted.

    Context options are "project", "asset", "task", "app"

    Deprecated:
        This function is deprecated and will be removed in future. Please use
        'addon applications extractenvironments ...' instead.
    """
    warnings.warn(
        (
            "Command 'extractenvironments' is deprecated and will be"
            " removed in future. Please use"
            " 'addon applications extractenvironments ...' instead."
        ),
        DeprecationWarning
    )

    addons_manager = ctx.obj["addons_manager"]
    applications_addon = addons_manager.get_enabled_addon("applications")
    if applications_addon is None:
        raise RuntimeError(
            "Applications addon is not available or enabled."
        )

    # Please ignore the fact this is using private method
    applications_addon._cli_extract_environments(
        output_json_path, project, asset, task, app, envgroup
    )


@main_cli.command()
@click.pass_context
@click.argument("path", required=True)
@click.option("-t", "--targets", help="Targets", default=None,
              multiple=True)
def publish(ctx, path, targets):
    """Start CLI publishing.

    Publish collects json from path provided as an argument.

    """
    from ayon_core.pipeline.publish import main_cli_publish

    main_cli_publish(path, targets, ctx.obj["addons_manager"])


@main_cli.command(context_settings={"ignore_unknown_options": True})
def publish_report_viewer():
    from ayon_core.tools.publisher.publish_report_viewer import main

    sys.exit(main())


@main_cli.command()
@click.argument("output_path")
@click.option("--project", help="Define project context")
@click.option("--folder", help="Define folder in project (project must be set)")
@click.option(
    "--strict",
    is_flag=True,
    help="Full context must be set otherwise dialog can't be closed."
)
def contextselection(
    output_path,
    project,
    folder,
    strict
):
    """Show Qt dialog to select context.

    Context is project name, folder path and task name. The result is stored
    into json file which path is passed in first argument.
    """
    from ayon_core.tools.context_dialog import main

    main(output_path, project, folder, strict)



@main_cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True))
@click.argument("script", required=True, type=click.Path(exists=True))
def run(script):
    """Run python script in AYON context."""
    import runpy

    if not script:
        print("Error: missing path to script file.")
        return

    # Remove first argument if it is the same as AYON executable
    # - Forward compatibility with future AYON versions.
    # - Current AYON launcher keeps the arguments with first argument but
    #     future versions might remove it.
    first_arg = sys.argv[0]
    if is_running_from_build():
        comp_path = os.getenv("AYON_EXECUTABLE")
    else:
        comp_path = os.path.join(os.environ["AYON_ROOT"], "start.py")
    # Compare paths and remove first argument if it is the same as AYON
    if Path(first_arg).resolve() == Path(comp_path).resolve():
        sys.argv.pop(0)

    # Remove 'run' command from sys.argv
    sys.argv.remove("run")

    args_string = " ".join(sys.argv[1:])
    print(f"... running: {script} {args_string}")
    runpy.run_path(script, run_name="__main__")


@main_cli.command()
def interactive():
    """Interactive (Python like) console.

    Helpful command not only for development to directly work with python
    interpreter.

    Warning:
        Executable 'ayon.exe' on Windows won't work.
    """
    version = os.environ["AYON_VERSION"]
    banner = (
        f"AYON launcher {version}\nPython {sys.version} on {sys.platform}"
    )
    code.interact(banner)


@main_cli.command()
@click.option("--build", help="Print only build version",
              is_flag=True, default=False)
def version(build):
    """Print AYON launcher version.

    Deprecated:
        This function has questionable usage.
    """
    print(os.environ["AYON_VERSION"])


def _set_global_environments() -> None:
    """Set global AYON environments."""
    general_env = get_general_environments()

    # first resolve general environment because merge doesn't expect
    # values to be list.
    # TODO: switch to AYON environment functions
    merged_env = acre.merge(
        acre.compute(acre.parse(general_env), cleanup=False),
        dict(os.environ)
    )
    env = acre.compute(
        merged_env,
        cleanup=False
    )
    os.environ.clear()
    os.environ.update(env)

    # Hardcoded default values
    os.environ["PYBLISH_GUI"] = "pyblish_pype"
    # Change scale factor only if is not set
    if "QT_AUTO_SCREEN_SCALE_FACTOR" not in os.environ:
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"


def _set_addons_environments(addons_manager):
    """Set global environments for AYON addons."""

    # Merge environments with current environments and update values
    if module_envs := addons_manager.collect_global_environments():
        parsed_envs = acre.parse(module_envs)
        env = acre.merge(parsed_envs, dict(os.environ))
        os.environ.clear()
        os.environ.update(env)


def _add_addons(addons_manager):
    """Modules/Addons can add their cli commands dynamically."""
    log = Logger.get_logger("CLI-AddAddons")
    for addon_obj in addons_manager.addons:
        try:
            addon_obj.cli(addon)

        except Exception:
            log.warning(
                "Failed to add cli command for module \"{}\"".format(
                    addon_obj.name
                ), exc_info=True
            )


def main(*args, **kwargs):
    initialize_ayon_connection()
    python_path = os.getenv("PYTHONPATH", "")
    split_paths = python_path.split(os.pathsep)

    additional_paths = [
        # add AYON tools for 'pyblish_pype'
        os.path.join(AYON_CORE_ROOT, "tools"),
        # add common AYON vendor
        # (common for multiple Python interpreter versions)
        os.path.join(AYON_CORE_ROOT, "vendor", "python")
    ]
    for path in additional_paths:
        if path not in split_paths:
            split_paths.insert(0, path)
        if path not in sys.path:
            sys.path.insert(0, path)
    os.environ["PYTHONPATH"] = os.pathsep.join(split_paths)

    print(">>> loading environments ...")
    print("  - global AYON ...")
    _set_global_environments()
    print("  - for addons ...")
    addons_manager = AddonsManager()
    _set_addons_environments(addons_manager)
    _add_addons(addons_manager)
    try:
        main_cli(
            prog_name="ayon",
            obj={"addons_manager": addons_manager},
        )
    except Exception:  # noqa
        exc_info = sys.exc_info()
        print("!!! AYON crashed:")
        traceback.print_exception(*exc_info)
        sys.exit(1)
