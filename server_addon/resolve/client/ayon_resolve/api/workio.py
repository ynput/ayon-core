"""Host API required Work Files tool"""

import os
from ayon_core.lib import Logger
from .lib import (
    get_project_manager,
    get_current_resolve_project
)


log = Logger.get_logger(__name__)


def file_extensions():
    return [".drp"]


def has_unsaved_changes():
    project_manager = get_project_manager()
    project_manager.SaveProject()
    return False


def save_file(filepath):
    project_manager = get_project_manager()
    file = os.path.basename(filepath)
    fname, _ = os.path.splitext(file)
    resolve_project = get_current_resolve_project()
    name = resolve_project.GetName()

    response = False
    if name == "Untitled Project":
        response = project_manager.CreateProject(fname)
        log.info("New project created: {}".format(response))
        project_manager.SaveProject()
    elif name != fname:
        response = resolve_project.SetName(fname)
        log.info("Project renamed: {}".format(response))

    exported = project_manager.ExportProject(fname, filepath)
    log.info("Project exported: {}".format(exported))


def open_file(filepath):
    """
    Loading project
    """

    from . import bmdvr

    project_manager = get_project_manager()
    page = bmdvr.GetCurrentPage()
    if page is not None:
        # Save current project only if Resolve has an active page, otherwise
        # we consider Resolve being in a pre-launch state (no open UI yet)
        resolve_project = get_current_resolve_project()
        print(f"Saving current resolve project: {resolve_project}")
        project_manager.SaveProject()

    file = os.path.basename(filepath)
    fname, _ = os.path.splitext(file)

    try:
        # load project from input path
        resolve_project = project_manager.LoadProject(fname)
        log.info(f"Project {resolve_project.GetName()} opened...")

    except AttributeError:
        log.warning((f"Project with name `{fname}` does not exist! It will "
                     f"be imported from {filepath} and then loaded..."))
        if project_manager.ImportProject(filepath):
            # load project from input path
            resolve_project = project_manager.LoadProject(fname)
            log.info(f"Project imported/loaded {resolve_project.GetName()}...")
            return True
        return False
    return True


def current_file():
    resolve_project = get_current_resolve_project()
    file_ext = file_extensions()[0]
    workdir_path = os.getenv("AYON_WORKDIR")

    project_name = resolve_project.GetName()
    file_name = project_name + file_ext

    # create current file path
    current_file_path = os.path.join(workdir_path, file_name)

    # return current file path if it exists
    if os.path.exists(current_file_path):
        return os.path.normpath(current_file_path)


def work_root(session):
    return os.path.normpath(session["AYON_WORKDIR"]).replace("\\", "/")
