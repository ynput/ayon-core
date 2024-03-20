import os
from ayon_core.lib import PreLaunchHook
from ayon_core.hosts.fusion import FUSION_HOST_DIR


class FusionLaunchMenuHook(PreLaunchHook):
    """Launch OpenPype menu on start of Fusion"""
    app_groups = ["fusion"]
    order = 9

    def execute(self):

        # TODO: Make this optional via project settings

        variant = self.application.name
        if variant.isnumeric():
            version = int(variant)
            if version < 18:
                print("Skipping launch of OpenPype menu on Fusion start "
                      "because Fusion version below 18.0 does not support "
                      "/execute argument on launch. "
                      f"Version detected: {version}")
                return
        else:
            print(f"Application variant is not numeric: {variant}. "
                  "Validation for Fusion version 18+ for /execute "
                  "prelaunch argument skipped.")

        path = os.path.join(FUSION_HOST_DIR,
                            "deploy",
                            "MenuScripts",
                            "launch_menu.py").replace("\\", "/")
        script = f"fusion:RunScript('{path}')"
        self.launch_context.launch_args.extend(["/execute", script])
