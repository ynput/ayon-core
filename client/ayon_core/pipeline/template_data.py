import ayon_api

from ayon_core.settings import get_studio_settings
from ayon_core.lib.local_settings import get_ayon_username


def get_general_template_data(settings=None):
    """General template data based on system settings or machine.

    Output contains formatting keys:
    - 'studio[name]'    - Studio name filled from system settings
    - 'studio[code]'    - Studio code filled from system settings
    - 'user'            - User's name using 'get_ayon_username'

    Args:
        settings (Dict[str, Any]): Studio or project settings.
    """

    if not settings:
        settings = get_studio_settings()
    core_settings = settings["core"]
    return {
        "studio": {
            "name": core_settings["studio_name"],
            "code": core_settings["studio_code"]
        },
        "user": get_ayon_username()
    }


def get_project_template_data(project_entity=None, project_name=None):
    """Extract data from project document that are used in templates.

    Project document must have 'name' and 'code'.

    One of 'project_name' or 'project_entity' must be passed. With prepared
    project document is function much faster because don't have to query.

    Output contains formatting keys:
    - 'project[name]'   - Project name
    - 'project[code]'   - Project code

    Args:
        project_entity (Dict[str, Any]): Queried project entity.
        project_name (str): Name of project.

    Returns:
        Dict[str, Dict[str, str]]: Template data based on project document.
    """

    if not project_name:
        project_name = project_entity["name"]

    elif not project_entity:
        project_entity = ayon_api.get_project(project_name, fields=["code"])

    project_code = project_entity["code"]
    return {
        "project": {
            "name": project_name,
            "code": project_code
        }
    }


def get_folder_template_data(folder_entity, project_name):
    """Extract data from folder entity that are used in templates.

    Output dictionary contains keys:
    - 'folder'      - dictionary with 'name' key filled with folder name
    - 'asset'       - folder name
    - 'hierarchy'   - parent folder names joined with '/'
    - 'parent'      - direct parent name, project name used if is under
                      project

    Required entity fields:
        Folder: 'path', 'folderType'

    Args:
        folder_entity (Dict[str, Any]): Folder entity.
        project_name (str): Is used for 'parent' key if folder entity
            does not have any.

    Returns:
        Dict[str, str]: Data that are based on folder entity and can be used
            in templates.
    """

    path = folder_entity["path"]
    hierarchy_parts = path.split("/")
    # Remove empty string from the beginning
    hierarchy_parts.pop(0)
    # Remove last part which is folder name
    folder_name = hierarchy_parts.pop(-1)
    hierarchy = "/".join(hierarchy_parts)
    if hierarchy_parts:
        parent_name = hierarchy_parts[-1]
    else:
        parent_name = project_name

    return {
        "folder": {
            "name": folder_name,
            "type": folder_entity["folderType"],
            "path": path,
        },
        "asset": folder_name,
        "hierarchy": hierarchy,
        "parent": parent_name
    }


def get_task_template_data(project_entity, task_entity):
    """Prepare task template data.

    Required document fields:
        Project: 'tasksTypes'
        Task: 'type'

    Args:
        project_entity (Dict[str, Any]): Project entity.
        task_entity (Dict[str, Any]): Task entity.

    Returns:
        Dict[str, Dict[str, str]]: Template data

    """
    project_task_types = project_entity["taskTypes"]
    task_types_by_name = {task["name"]: task for task in project_task_types}
    task_type = task_entity["taskType"]
    task_code = task_types_by_name.get(task_type, {}).get("shortName")

    return {
        "task": {
            "name": task_entity["name"],
            "type": task_type,
            "short": task_code,
        }
    }


def get_template_data(
    project_entity,
    folder_entity=None,
    task_entity=None,
    host_name=None,
    settings=None,
):
    """Prepare data for templates filling from entered documents and info.

    This function does not "auto fill" any values except system settings and
    it's on purpose.

    Universal function to receive template data from passed arguments. Only
    required argument is project document all other arguments are optional
    and their values won't be added to template data if are not passed.

    Required document fields:
        Project: 'name', 'code', 'taskTypes.name'
        Folder: 'name', 'path'
        Task: 'type'

    Args:
        project_entity (Dict[str, Any]): Project entity.
        folder_entity (Optional[Dict[str, Any]]): Folder entity.
        task_entity (Optional[Dict[str, Any]): Task entity.
        host_name (Optional[str]): Used to fill '{app}' key.
        settings (Union[Dict, None]): Prepared studio or project settings.
            They're queried if not passed (may be slower).

    Returns:
        Dict[str, Any]: Data prepared for filling workdir template.
    """

    template_data = get_general_template_data(settings)
    template_data.update(get_project_template_data(project_entity))
    if folder_entity:
        template_data.update(get_folder_template_data(
            folder_entity, project_entity["name"]
        ))
        if task_entity:
            template_data.update(get_task_template_data(
                project_entity, task_entity
            ))

    if host_name:
        template_data["app"] = host_name

    return template_data


def get_template_data_with_names(
    project_name,
    folder_path=None,
    task_name=None,
    host_name=None,
    settings=None
):
    """Prepare data for templates filling from entered entity names and info.

    Copy of 'get_template_data' but based on entity names instead of documents.
    Only difference is that documents are queried.

    Args:
        project_name (str): Project name.
        folder_path (Optional[str]): Folder path.
        task_name (Optional[str]): Task name.
        host_name (Optional[str]):Used to fill '{app}' key.
            because workdir template may contain `{app}` key.
        settings (Optional[Dict]): Prepared studio or project settings.
            They're queried if not passed.

    Returns:
        Dict[str, Any]: Data prepared for filling workdir template.
    """

    project_entity = ayon_api.get_project(project_name)
    folder_entity = None
    task_entity = None
    if folder_path:
        folder_entity = ayon_api.get_folder_by_path(
            project_name,
            folder_path,
            fields={"id", "path", "folderType"}
        )
        if task_name and folder_entity:
            task_entity = ayon_api.get_task_by_name(
                project_name, folder_entity["id"], task_name
            )
    return get_template_data(
        project_entity, folder_entity, task_entity, host_name, settings
    )
