from ayon_core.addon import AYONAddon, IHostAddon


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
