import os
from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__

CELACTION_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


class CelactionAddon(AYONAddon, IHostAddon):
    name = "celaction"
    version = __version__
    host_name = "celaction"

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(CELACTION_ROOT_DIR, "hooks")
        ]

    def add_implementation_envs(self, env, _app):
        # Set default values if are not already set via settings
        defaults = {
            "LOGLEVEL": "DEBUG"
        }
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

    def get_workfile_extensions(self):
        return [".scn"]
