# -*- coding: utf-8 -*-
import os
from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__

MAX_HOST_DIR = os.path.dirname(os.path.abspath(__file__))


class MaxAddon(AYONAddon, IHostAddon):
    name = "max"
    version = __version__
    host_name = "max"

    def add_implementation_envs(self, env, _app):
        # Remove auto screen scale factor for Qt
        # - let 3dsmax decide it's value
        env.pop("QT_AUTO_SCREEN_SCALE_FACTOR", None)

    def get_workfile_extensions(self):
        return [".max"]

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(MAX_HOST_DIR, "hooks")
        ]
