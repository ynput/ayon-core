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
    max_script = project_settings["max"].get("mxp_workspace")
    # TODO: add ProjectFolder={workdir} into the max_script
    edited_script = "\n".join((
        '[Directories]',
        f'ProjectFolder={workdir}'
    ))
    max_script = max_script.replace("[Directories]", edited_script)
    # Skip if mxp script in settings is empty
    if not max_script:
        log = Logger.get_logger("create_workspace_mxp")
        log.debug("File 'workspace.mxp' not created. Settings value is empty.")
        return

    with open(dst_filepath, "w") as mxp_file:
        mxp_file.write(max_script)
