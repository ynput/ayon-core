import os
from ayon_core.settings import get_project_settings
from ayon_core.lib import Logger


def create_workspace_mxp(workdir, project_name):
    dst_filepath = os.path.join(workdir, "workspace.mxp")
    if os.path.exists(dst_filepath):
        return

    if not os.path.exists(workdir):
        os.makedirs(workdir)

    project_settings = get_project_settings(project_name)
    log = Logger.get_logger("create_workspace_mxp")
    mxp_workspace = project_settings["max"].get("mxp_workspace")
    # Ensure the hook would not cause possible error
    # when using the old addon.
    if mxp_workspace is None:
        log.debug("No mxp workspace setting found in the "
                  "latest Max Addon. Please update to 0.1.8")
        return
    if mxp_workspace.get("enabled_project_creation"):
        max_script = mxp_workspace.get("mxp_workspace_script")
        # Skip if mxp script in settings is empty
        if not max_script:
            log.debug("File 'workspace.mxp' not created. Settings value is empty.")
            return

        with open(dst_filepath, "w") as mxp_file:
            mxp_file.write(max_script)

        return dst_filepath
