import os

from ayon_core.addon import AYONAddon, IHostAddon

from .utils import RESOLVE_ROOT_DIR


class ResolveAddon(AYONAddon, IHostAddon):
    name = "resolve"
    host_name = "resolve"

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(RESOLVE_ROOT_DIR, "hooks")
        ]

    def get_workfile_extensions(self):
        return [".drp"]
