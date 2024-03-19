# -*- coding: utf-8 -*-
"""Package for handling AYON command line arguments."""
import os
import sys
import code
import traceback

import click
import acre

from ayon_core import AYON_CORE_ROOT
from ayon_core.addon import AddonsManager
from ayon_core.settings import get_general_environments
from ayon_core.lib import initialize_ayon_connection

from .cli_commands import Commands


class AliasedGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases = {}

    def set_alias(self, src_name, dst_name):
        self._aliases[dst_name] = src_name

    def get_command(self, ctx, cmd_name):
        if cmd_name in self._aliases:
            cmd_name = self._aliases[cmd_name]
        return super().get_command(ctx, cmd_name)


@click.group(cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
@click.option("--use-staging", is_flag=True,
              expose_value=False, help="use staging variants")
@click.option("--debug", is_flag=True, expose_value=False,
              help="Enable debug")
@click.option("--verbose", expose_value=False,
              help=("Change AYON log level (debug - critical or 0-50)"))
def main_cli(ctx):
    """AYON is main command serving as entry point to pipeline system.

    It wraps different commands together.
    """

    if ctx.invoked_subcommand is None:
        # Print help if headless mode is used
        if os.getenv("AYON_HEADLESS_MODE") == "1":
            print(ctx.get_help())
            sys.exit(0)
        else:
            ctx.invoke(tray)


@main_cli.command()
def tray():
    """Launch AYON tray.

    Default action of AYON command is to launch tray widget to control basic
    aspects of AYON. See documentation for more information.
    """
    Commands.launch_tray()


@Commands.add_addons
@main_cli.group(help="Run command line arguments of AYON addons")
@click.pass_context
def addon(ctx):
    """Addon specific commands created dynamically.

    These commands are generated dynamically by currently loaded addons.
    """
    pass


# Add 'addon' as alias for module
main_cli.set_alias("addon", "module")


@main_cli.command()
@click.argument("output_json_path")
@click.option("--project", help="Project name", default=None)
@click.option("--folder", help="Folder path", default=None)
@click.option("--task", help="Task name", default=None)
@click.option("--app", help="Application name", default=None)
@click.option(
    "--envgroup", help="Environment group (e.g. \"farm\")", default=None
)
def extractenvironments(output_json_path, project, folder, task, app, envgroup):
    """Extract environment variables for entered context to a json file.

    Entered output filepath will be created if does not exists.

    All context options must be passed otherwise only AYON's global
    environments will be extracted.

    Context options are "project", "folder", "task", "app"
    """
    Commands.extractenvironments(
        output_json_path, project, folder, task, app, envgroup
    )


@main_cli.command()
@click.argument("path", required=True)
@click.option("-t", "--targets", help="Targets", default=None,
              multiple=True)
@click.option("-g", "--gui", is_flag=True,
              help="Show Publish UI", default=False)
def publish(path, targets, gui):
    """Start CLI publishing.

    Publish collects json from path provided as an argument.
S
    """
    Commands.publish(path, targets, gui)


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
    Commands.contextselection(
        output_path,
        project,
        folder,
        strict
    )


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
    else:

        args = sys.argv
        args.remove("run")
        args.remove(script)
        sys.argv = args

        args_string = " ".join(args[1:])
        print(f"... running: {script} {args_string}")
        runpy.run_path(script, run_name="__main__", )


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


def _set_addons_environments():
    """Set global environments for AYON addons."""

    addons_manager = AddonsManager()

    # Merge environments with current environments and update values
    if module_envs := addons_manager.collect_global_environments():
        parsed_envs = acre.parse(module_envs)
        env = acre.merge(parsed_envs, dict(os.environ))
        os.environ.clear()
        os.environ.update(env)


def main(*args, **kwargs):
    initialize_ayon_connection()
    python_path = os.getenv("PYTHONPATH", "")
    split_paths = python_path.split(os.pathsep)

    additional_paths = [
        # add AYON tools for 'pyblish_pype'
        os.path.join(AYON_CORE_ROOT, "tools"),
        # add common AYON vendor
        # (common for multiple Python interpreter versions)
        os.path.join(AYON_CORE_ROOT, "vendor", "python", "common")
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
    _set_addons_environments()

    try:
        main_cli(obj={}, prog_name="ayon")
    except Exception:  # noqa
        exc_info = sys.exc_info()
        print("!!! AYON crashed:")
        traceback.print_exception(*exc_info)
        sys.exit(1)
