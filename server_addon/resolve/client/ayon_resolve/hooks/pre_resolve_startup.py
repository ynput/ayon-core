import os

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_resolve import RESOLVE_ADDON_ROOT


class PreLaunchResolveStartup(PreLaunchHook):
    """Special hook to configure startup script.

    """
    order = 11
    app_groups = {"resolve"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        # Set the openpype prelaunch startup script path for easy access
        # in the LUA .scriptlib code
        script_path = os.path.join(RESOLVE_ADDON_ROOT, "startup.py")
        key = "AYON_RESOLVE_STARTUP_SCRIPT"
        self.launch_context.env[key] = script_path

        self.log.info(
            f"Setting AYON_RESOLVE_STARTUP_SCRIPT to: {script_path}"
        )
