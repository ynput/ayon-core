from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.hosts.maya.lib import create_workspace_mel


class PreCopyMel(PreLaunchHook):
    """Copy workspace.mel to workdir.

    Hook `GlobalHostDataHook` must be executed before this hook.
    """
    app_groups = {"maya", "mayapy"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        project_entity = self.data["project_entity"]
        workdir = self.launch_context.env.get("AYON_WORKDIR")
        if not workdir:
            self.log.warning("BUG: Workdir is not filled.")
            return

        project_settings = self.data["project_settings"]
        create_workspace_mel(
            workdir, project_entity["name"], project_settings
        )
