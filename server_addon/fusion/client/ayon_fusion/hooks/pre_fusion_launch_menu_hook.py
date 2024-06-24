import os
from ayon_applications import PreLaunchHook
from ayon_fusion import FUSION_ADDON_ROOT


class FusionLaunchMenuHook(PreLaunchHook):
    """Launch AYON menu on start of Fusion"""
    app_groups = ["fusion"]
    order = 9

    def execute(self):
        # Prelaunch hook is optional
        settings = self.data["project_settings"][self.host_name]
        if not settings["hooks"]["FusionLaunchMenuHook"]["enabled"]:
            return

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

        path = os.path.join(FUSION_ADDON_ROOT,
                            "deploy",
                            "MenuScripts",
                            "launch_menu.py").replace("\\", "/")
        script = f"fusion:RunScript('{path}')"
        self.launch_context.launch_args.extend(["/execute", script])
