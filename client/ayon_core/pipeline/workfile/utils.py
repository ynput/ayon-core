from ayon_core.lib import filter_profiles
from ayon_core.settings import get_project_settings


def should_use_last_workfile_on_launch(
    project_name,
    host_name,
    task_name,
    task_type,
    default_output=False,
    project_settings=None,
):
    """Define if host should start last version workfile if possible.

    Default output is `False`. Can be overridden with environment variable
    `AYON_OPEN_LAST_WORKFILE`, valid values without case sensitivity are
    `"0", "1", "true", "false", "yes", "no"`.

    Args:
        project_name (str): Name of project.
        host_name (str): Name of host which is launched. In avalon's
            application context it's value stored in app definition under
            key `"application_dir"`. Is not case sensitive.
        task_name (str): Name of task which is used for launching the host.
            Task name is not case sensitive.
        task_type (str): Task type.
        default_output (Optional[bool]): Default output value if no profile
            is found.
        project_settings (Optional[dict[str, Any]]): Project settings.

    Returns:
        bool: True if host should start workfile.

    """
    if project_settings is None:
        project_settings = get_project_settings(project_name)
    profiles = (
        project_settings
        ["core"]
        ["tools"]
        ["Workfiles"]
        ["last_workfile_on_startup"]
    )

    if not profiles:
        return default_output

    filter_data = {
        "tasks": task_name,
        "task_types": task_type,
        "hosts": host_name
    }
    matching_item = filter_profiles(profiles, filter_data)

    output = None
    if matching_item:
        output = matching_item.get("enabled")

    if output is None:
        return default_output
    return output


def should_open_workfiles_tool_on_launch(
    project_name,
    host_name,
    task_name,
    task_type,
    default_output=False,
    project_settings=None,
):
    """Define if host should start workfile tool at host launch.

    Default output is `False`. Can be overridden with environment variable
    `AYON_WORKFILE_TOOL_ON_START`, valid values without case sensitivity are
    `"0", "1", "true", "false", "yes", "no"`.

    Args:
        project_name (str): Name of project.
        host_name (str): Name of host which is launched. In avalon's
            application context it's value stored in app definition under
            key `"application_dir"`. Is not case sensitive.
        task_name (str): Name of task which is used for launching the host.
            Task name is not case sensitive.
        task_type (str): Task type.
        default_output (Optional[bool]): Default output value if no profile
            is found.
        project_settings (Optional[dict[str, Any]]): Project settings.

    Returns:
        bool: True if host should start workfile.

    """

    if project_settings is None:
        project_settings = get_project_settings(project_name)
    profiles = (
        project_settings
        ["core"]
        ["tools"]
        ["Workfiles"]
        ["open_workfile_tool_on_startup"]
    )

    if not profiles:
        return default_output

    filter_data = {
        "tasks": task_name,
        "task_types": task_type,
        "hosts": host_name
    }
    matching_item = filter_profiles(profiles, filter_data)

    output = None
    if matching_item:
        output = matching_item.get("enabled")

    if output is None:
        return default_output
    return output
