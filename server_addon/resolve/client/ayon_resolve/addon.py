import os

from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__
from .utils import RESOLVE_ADDON_ROOT


class ResolveAddon(AYONAddon, IHostAddon):
    name = "resolve"
    version = __version__
    host_name = "resolve"

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(RESOLVE_ADDON_ROOT, "hooks")
        ]

    def get_workfile_extensions(self):
        return [".drp"]
