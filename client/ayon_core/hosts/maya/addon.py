import os
from ayon_core.addon import AYONAddon, IHostAddon

MAYA_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


class MayaAddon(AYONAddon, IHostAddon):
    name = "maya"
    host_name = "maya"

    def add_implementation_envs(self, env, _app):
        # Add requirements to PYTHONPATH
        new_python_paths = [
            os.path.join(MAYA_ROOT_DIR, "startup")
        ]
        old_python_path = env.get("PYTHONPATH") or ""
        for path in old_python_path.split(os.pathsep):
            if not path:
                continue

            norm_path = os.path.normpath(path)
            if norm_path not in new_python_paths:
                new_python_paths.append(norm_path)

        # add vendor path
        new_python_paths.append(
            os.path.join(MAYA_ROOT_DIR, "vendor", "python")
        )
        env["PYTHONPATH"] = os.pathsep.join(new_python_paths)

        # Set default environments
        envs = {
            "AYON_LOG_NO_COLORS": "1",
        }
        for key, value in envs.items():
            env[key] = value

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(MAYA_ROOT_DIR, "hooks")
        ]

    def get_workfile_extensions(self):
        return [".ma", ".mb"]
