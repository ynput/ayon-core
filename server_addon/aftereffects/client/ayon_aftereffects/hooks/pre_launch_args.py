import os
import platform
import subprocess

from ayon_core.lib import (
    get_ayon_launcher_args,
    is_using_ayon_console,
)
from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_aftereffects import get_launch_script_path


def get_launch_kwargs(kwargs):
    """Explicit setting of kwargs for Popen for AfterEffects.

    Expected behavior
    - ayon_console opens window with logs
    - ayon has stdout/stderr available for capturing

    Args:
        kwargs (Union[dict, None]): Current kwargs or None.

    """
    if kwargs is None:
        kwargs = {}

    if platform.system().lower() != "windows":
        return kwargs

    if is_using_ayon_console():
        kwargs.update({
            "creationflags": subprocess.CREATE_NEW_CONSOLE
        })
    else:
        kwargs.update({
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL
        })
    return kwargs


class AEPrelaunchHook(PreLaunchHook):
    """Launch arguments preparation.

    Hook add python executable and script path to AE implementation before
    AE executable and add last workfile path to launch arguments.

    Existence of last workfile is checked. If workfile does not exists tries
    to copy templated workfile from predefined path.
    """
    app_groups = {"aftereffects"}

    order = 20
    launch_types = {LaunchTypes.local}

    def execute(self):
        # Pop executable
        executable_path = self.launch_context.launch_args.pop(0)

        # Pop rest of launch arguments - There should not be other arguments!
        remainders = []
        while self.launch_context.launch_args:
            remainders.append(self.launch_context.launch_args.pop(0))

        script_path = get_launch_script_path()

        new_launch_args = get_ayon_launcher_args(
            "run", script_path, executable_path
        )
        # Add workfile path if exists
        workfile_path = self.data["last_workfile_path"]
        if (
            self.data.get("start_last_workfile")
            and workfile_path
            and os.path.exists(workfile_path)
        ):
            new_launch_args.append(workfile_path)

        # Append as whole list as these arguments should not be separated
        self.launch_context.launch_args.append(new_launch_args)

        if remainders:
            self.launch_context.launch_args.extend(remainders)

        self.launch_context.kwargs = get_launch_kwargs(
            self.launch_context.kwargs
        )
