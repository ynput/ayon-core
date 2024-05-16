import os
from ayon_core.addon import AYONAddon, IHostAddon

HARMONY_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class HarmonyAddon(AYONAddon, IHostAddon):
    name = "harmony"
    host_name = "harmony"

    def add_implementation_envs(self, env, _app):
        """Modify environments to contain all required for implementation."""
        openharmony_path = os.path.join(
            HARMONY_ADDON_ROOT, "vendor", "OpenHarmony"
        )
        # TODO check if is already set? What to do if is already set?
        env["LIB_OPENHARMONY_PATH"] = openharmony_path

    def get_workfile_extensions(self):
        return [".zip"]

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(HARMONY_ADDON_ROOT, "hooks")
        ]


def get_launch_script_path():
    return os.path.join(
        HARMONY_ADDON_ROOT, "api", "launch_script.py"
    )
