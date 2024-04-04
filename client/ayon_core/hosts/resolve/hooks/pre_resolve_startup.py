import os

from ayon_applications import PreLaunchHook, LaunchTypes
import ayon_core.hosts.resolve


class PreLaunchResolveStartup(PreLaunchHook):
    """Special hook to configure startup script.

    """
    order = 11
    app_groups = {"resolve"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        # Set the openpype prelaunch startup script path for easy access
        # in the LUA .scriptlib code
        op_resolve_root = os.path.dirname(ayon_core.hosts.resolve.__file__)
        script_path = os.path.join(op_resolve_root, "startup.py")
        key = "AYON_RESOLVE_STARTUP_SCRIPT"
        self.launch_context.env[key] = script_path

        self.log.info(
            f"Setting AYON_RESOLVE_STARTUP_SCRIPT to: {script_path}"
        )
