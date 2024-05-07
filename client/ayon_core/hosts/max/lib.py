import os
from ayon_core.settings import get_project_settings
from ayon_core.lib import Logger


def create_workspace_mxp(workdir, project_name, project_settings=None):
    dst_filepath = os.path.join(workdir, "workspace.mxp")
    if os.path.exists(dst_filepath):
        return

    if not os.path.exists(workdir):
        os.makedirs(workdir)

    if not project_settings:
        project_settings = get_project_settings(project_name)
    log = Logger.get_logger("create_workspace_mxp")
    mxp_workspace = project_settings["max"].get("mxp_workspace")
    # Ensure the hook would not cause possible error
    # when using the old addon.
    if mxp_workspace is None:
        log.debug("No mxp workspace setting found in the "
                  "latest Max Addon. Please update to 0.1.8")
        return
    if not mxp_workspace.get("enabled"):
        log.debug("Mxp workspace disabled in the project settings."
                  " Skipping action.")
        return
    max_script = mxp_workspace.get("mxp_workspace_script")
    # Skip if mxp script in settings is empty
    if not max_script:
        log.debug("File 'workspace.mxp' not created. Settings value is empty.")
        return

    edited_script = "\n".join((
        '[Directories]',
        f'ProjectFolder={workdir}'
    ))
    max_script = max_script.replace("[Directories]", edited_script)

    with open(dst_filepath, "w") as mxp_file:
        mxp_file.write(max_script)
