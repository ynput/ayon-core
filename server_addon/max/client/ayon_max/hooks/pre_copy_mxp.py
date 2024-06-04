from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_max.mxp import create_workspace_mxp


class PreCopyMxp(PreLaunchHook):
    """Copy workspace.mxp to workdir.

    Hook `GlobalHostDataHook` must be executed before this hook.
    """
    app_groups = {"3dsmax", "adsk_3dsmax"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        project_entity = self.data["project_entity"]
        workdir = self.launch_context.env.get("AYON_WORKDIR")
        if not workdir:
            self.log.warning("BUG: Workdir is not filled.")
            return

        create_workspace_mxp(workdir, project_entity["name"])
