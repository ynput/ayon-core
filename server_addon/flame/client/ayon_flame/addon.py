import os
from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__

FLAME_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class FlameAddon(AYONAddon, IHostAddon):
    name = "flame"
    version = __version__
    host_name = "flame"

    def add_implementation_envs(self, env, _app):
        # Add requirements to DL_PYTHON_HOOK_PATH
        env["DL_PYTHON_HOOK_PATH"] = os.path.join(FLAME_ADDON_ROOT, "startup")
        env.pop("QT_AUTO_SCREEN_SCALE_FACTOR", None)

        # Set default values if are not already set via settings
        defaults = {
            "LOGLEVEL": "DEBUG"
        }
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(FLAME_ADDON_ROOT, "hooks")
        ]

    def get_workfile_extensions(self):
        return [".otoc"]
