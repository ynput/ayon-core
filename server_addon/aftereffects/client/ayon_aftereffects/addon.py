import os

from ayon_core.addon import AYONAddon, IHostAddon

AFTEREFFECTS_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class AfterEffectsAddon(AYONAddon, IHostAddon):
    name = "aftereffects"
    host_name = "aftereffects"

    def add_implementation_envs(self, env, _app):
        """Modify environments to contain all required for implementation."""
        defaults = {
            "AYON_LOG_NO_COLORS": "1",
            "WEBSOCKET_URL": "ws://localhost:8097/ws/"
        }
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

    def get_workfile_extensions(self):
        return [".aep"]

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(AFTEREFFECTS_ADDON_ROOT, "hooks")
        ]


def get_launch_script_path():
    return os.path.join(
        AFTEREFFECTS_ADDON_ROOT, "api", "launch_script.py"
    )
