import os
from ayon_core.modules import OpenPypeModule, IHostAddon

PHOTOSHOP_HOST_DIR = os.path.dirname(os.path.abspath(__file__))


class PhotoshopAddon(OpenPypeModule, IHostAddon):
    name = "photoshop"
    host_name = "photoshop"

    def initialize(self, module_settings):
        self.enabled = True

    def add_implementation_envs(self, env, _app):
        """Modify environments to contain all required for implementation."""
        defaults = {
            "AYON_LOG_NO_COLORS": "1",
            "WEBSOCKET_URL": "ws://localhost:8099/ws/"
        }
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

    def get_workfile_extensions(self):
        return [".psd", ".psb"]
