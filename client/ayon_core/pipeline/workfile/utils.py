from __future__ import annotations
import os
import platform
import uuid
import typing
from typing import Optional, Any

import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import filter_profiles, emit_event, get_ayon_username
from ayon_core.settings import get_project_settings

from .path_resolving import (
    create_workdir_extra_folders,
    get_workfile_template_key,
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class MissingWorkdirError(Exception):
    """Raised when accessing a work directory not found on disk."""
    pass


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


def _get_event_context_data(
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
):
    return {
        "project_name": project_name,
        "folder_id": folder_entity["id"],
        "folder_path": folder_entity["path"],
        "task_id": task_entity["id"],
        "task_name": task_entity["name"],
        "host_name": host_name,
    }


def save_workfile_info(
    project_name: str,
    task_id: str,
    rootless_path: str,
    host_name: str,
    version: Optional[int],
    comment: Optional[str],
    description: Optional[str],
    username: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
):
    # TODO create pipeline function for this
    if workfile_entities is None:
        workfile_entities = list(ayon_api.get_workfiles_info(
            project_name,
            task_ids=[task_id],
        ))

    workfile_entity = next(
        (
            _ent
            for _ent in workfile_entities
            if _ent["path"] == rootless_path
        ),
        None
    )

    if username is None:
        username = get_ayon_username()

    if not workfile_entity:
        return _create_workfile_info_entity(
            project_name,
            task_id,
            host_name,
            rootless_path,
            username,
            version,
            comment,
            description,
        )

    data = {}
    for key, value in (
        ("host_name", host_name),
        ("version", version),
        ("comment", comment),
    ):
        if value is not None:
            data[key] = value

    old_data = workfile_entity["data"]

    changed_data = {}
    for key, value in data.items():
        if key not in old_data or old_data[key] != value:
            changed_data[key] = value

    update_data = {}
    if changed_data:
        update_data["data"] = changed_data

    old_description = workfile_entity["attrib"].get("description")
    if description is not None and old_description != description:
        update_data["attrib"] = {"description": description}
        workfile_entity["attrib"]["description"] = description

    # Automatically fix 'createdBy' and 'updatedBy' fields
    # NOTE both fields were not automatically filled by server
    #   until 1.1.3 release.
    if workfile_entity.get("createdBy") is None:
        update_data["createdBy"] = username
        workfile_entity["createdBy"] = username

    if workfile_entity.get("updatedBy") != username:
        update_data["updatedBy"] = username
        workfile_entity["updatedBy"] = username

    if not update_data:
        return

    session = OperationsSession()
    session.update_entity(
        project_name,
        "workfile",
        workfile_entity["id"],
        update_data,
    )
    session.commit()
    return workfile_entity


def open_workfile(
    filepath: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
):
    from ayon_core.pipeline.context_tools import (
        registered_host, change_current_context
    )

    # Trigger before save event
    host = registered_host()
    context = host.get_current_context()
    project_name = context["project_name"]
    current_folder_path = context["folder_path"]
    current_task_name = context["task_name"]
    host_name = host.name

    # TODO move to workfiles pipeline
    event_data = _get_event_context_data(
        project_name, folder_entity, task_entity, host_name
    )
    event_data["filepath"] = filepath

    emit_event("workfile.open.before", event_data, source="workfiles.tool")

    # Change context
    if (
        folder_entity["path"] != current_folder_path
        or task_entity["name"] != current_task_name
    ):
        change_current_context(
            project_name,
            folder_entity,
            task_entity,
            workdir=os.path.dirname(filepath)
        )

    host.open_workfile_with_context(
        filepath,
        folder_entity["id"],
        task_entity["id"],
        folder_entity,
        task_entity,
    )

    emit_event("workfile.open.after", event_data, source="workfiles.tool")


def save_current_workfile_to(
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    version: Optional[int],
    comment: Optional[str] = None,
    description: Optional[str] = None,
    source: Optional[str] = None,
    rootless_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    username: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
) -> dict[str, Any]:
    """Save current workfile to new location or context.

    Args:
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        source (Optional[str]): Source of the save action.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        username (Optional[str]): Username of the user saving the workfile.
            Current user is used if not passed.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    print("save_current_workfile_to")
    return _save_workfile(
        None,
        None,
        None,
        None,
        workfile_path,
        folder_entity,
        task_entity,
        version,
        comment,
        description,
        source,
        rootless_path,
        workfile_entities,
        username,
        project_entity,
        project_settings,
        anatomy,
    )


def copy_and_open_workfile(
    src_workfile_path: str,
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    version: Optional[int],
    comment: Optional[str] = None,
    description: Optional[str] = None,
    source: Optional[str] = None,
    rootless_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    username: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
) -> dict[str, Any]:
    """Copy workfile to new location and open it.

    Args:
        src_workfile_path (str): Source workfile path.
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        source (Optional[str]): Source of the save action.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        username (Optional[str]): Username of the user saving the workfile.
            Current user is used if not passed.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    print("copy_and_open_workfile")
    return _save_workfile(
        src_workfile_path,
        None,
        None,
        None,
        workfile_path,
        folder_entity,
        task_entity,
        version,
        comment,
        description,
        source,
        rootless_path,
        workfile_entities,
        username,
        project_entity,
        project_settings,
        anatomy,
    )


def copy_and_open_workfile_representation(
    project_name: str,
    representation_id: str,
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    version: Optional[int],
    comment: Optional[str] = None,
    description: Optional[str] = None,
    source: Optional[str] = None,
    rootless_path: Optional[str] = None,
    representation_entity: Optional[dict[str, Any]] = None,
    representation_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    username: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
) -> dict[str, Any]:
    """Copy workfile to new location and open it.

    Args:
        project_name (str): Project name where representation is stored.
        representation_id (str): Source representation id.
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        source (Optional[str]): Source of the save action.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        username (Optional[str]): Username of the user saving the workfile.
            Current user is used if not passed.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    print("copy_and_open_workfile_representation")
    if representation_entity is None:
        representation_entity = ayon_api.get_representation_by_id(
            project_name,
            representation_id,
        )

    return _save_workfile(
        None,
        project_name,
        representation_entity,
        representation_path,
        workfile_path,
        folder_entity,
        task_entity,
        version,
        comment,
        description,
        source,
        rootless_path,
        workfile_entities,
        username,
        project_entity,
        project_settings,
        anatomy,
    )


def _save_workfile(
    src_workfile_path: Optional[str],
    representation_project_name: Optional[str],
    representation_entity: Optional[dict[str, Any]],
    representation_path: Optional[str],
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    version: Optional[int],
    comment: Optional[str],
    description: Optional[str],
    source: Optional[str],
    rootless_path: Optional[str],
    workfile_entities: Optional[list[dict[str, Any]]],
    username: Optional[str],
    project_entity: Optional[dict[str, Any]],
    project_settings: Optional[dict[str, Any]],
    anatomy: Optional["Anatomy"],
) -> dict[str, Any]:
    """Function used to save workfile to new location and context.

    Because the functionality for 'save_current_workfile_to' and
        'copy_and_open_workfile' is currently the same, except for used
        function on host it is easier to create this wrapper function.

    Args:
        src_workfile_path (Optional[str]): Source workfile path.
        representation_entity (Optional[dict[str, Any]]): Representation used
            as source for workfile.
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        source (Optional[str]): Source of the save action.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        username (Optional[str]): Username of the user saving the workfile.
            Current user is used if not passed.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    from ayon_core.pipeline.context_tools import (
        registered_host, change_current_context
    )

    # Trigger before save event
    host = registered_host()
    context = host.get_current_context()
    project_name = context["project_name"]
    current_folder_path = context["folder_path"]
    current_task_name = context["task_name"]

    folder_id = folder_entity["id"]
    task_name = task_entity["name"]
    task_type = task_entity["taskType"]
    task_id = task_entity["id"]
    host_name = host.name

    workdir, filename = os.path.split(workfile_path)

    # QUESTION should the data be different for 'before' and 'after'?
    event_data = _get_event_context_data(
        project_name, folder_entity, task_entity, host_name
    )
    event_data.update({
        "filename": filename,
        "workdir_path": workdir,
    })

    emit_event("workfile.save.before", event_data, source=source)

    # Change context
    if (
        folder_entity["path"] != current_folder_path
        or task_entity["name"] != current_task_name
    ):
        change_current_context(
            folder_entity,
            task_entity,
            workdir=workdir,
            anatomy=anatomy,
            project_entity=project_entity,
            project_settings=project_settings,
        )

    if src_workfile_path:
        host.copy_workfile(
            src_workfile_path,
            workfile_path,
            folder_id,
            task_id,
            open_workfile=True,
            dst_folder_entity=folder_entity,
            dst_task_entity=task_entity,
        )
    elif representation_entity:
        host.copy_workfile_representation(
            representation_project_name,
            representation_entity["id"],
            workfile_path,
            folder_id,
            task_id,
            open_workfile=True,
            folder_entity=folder_entity,
            task_entity=task_entity,
            src_representation_entity=representation_entity,
            src_representation_path=representation_path,
            anatomy=anatomy,
        )
    else:
        host.save_workfile_with_context(
            workfile_path,
            folder_id,
            task_id,
            open_workfile=True,
            folder_entity=folder_entity,
            task_entity=task_entity,
        )

    if not description:
        description = None

    if not comment:
        comment = None

    if rootless_path is None:
        rootless_path = _find_rootless_path(
            workfile_path,
            project_name,
            task_type,
            host_name,
            project_entity,
            project_settings,
            anatomy,
        )

    # It is not possible to create workfile infor without rootless path
    workfile_info = None
    if rootless_path:
        if platform.system().lower() == "windows":
            rootless_path = rootless_path.replace("\\", "/")

        workfile_info = save_workfile_info(
            project_name,
            task_id,
            rootless_path,
            host_name,
            version,
            comment,
            description,
            username=username,
            workfile_entities=workfile_entities,
        )

    # Create extra folders
    create_workdir_extra_folders(
        workdir,
        host.name,
        task_entity["taskType"],
        task_name,
        project_name
    )

    # Trigger after save events
    emit_event("workfile.save.after", event_data, source=source)
    return workfile_info


def _find_rootless_path(
    workfile_path: str,
    project_name: str,
    task_type: str,
    host_name: str,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
) -> str:
    """Find rootless workfile path."""
    if anatomy is None:
        from ayon_core.pipeline import Anatomy

        anatomy = Anatomy(project_name, project_entity=project_entity)
    template_key = get_workfile_template_key(
        project_name,
        task_type,
        host_name,
        project_settings=project_settings
    )
    dir_template = anatomy.get_template_item(
        "work", template_key, "directory"
    )
    result = dir_template.format({"root": anatomy.roots})
    used_root = result.used_values.get("root")
    rootless_path = str(workfile_path)
    if platform.system().lower() == "windows":
        rootless_path = rootless_path.replace("\\", "/")

    root_key = root_value = None
    if used_root is not None:
        root_key, root_value = next(iter(used_root.items()))
        if platform.system().lower() == "windows":
            root_value = root_value.replace("\\", "/")

    if root_value and rootless_path.startswith(root_value):
        rootless_path = rootless_path[len(root_value):].lstrip("/")
        rootless_path = f"{{root[{root_key}]}}/{rootless_path}"
    else:
        success, result = anatomy.find_root_template_from_path(rootless_path)
        if success:
            rootless_path = result
    return rootless_path


def _create_workfile_info_entity(
    project_name: str,
    task_id: str,
    host_name: str,
    rootless_path: str,
    username: str,
    version: Optional[int],
    comment: Optional[str],
    description: Optional[str],
) -> dict[str, Any]:
    extension = os.path.splitext(rootless_path)[1]

    attrib = {}
    for key, value in (
        ("extension", extension),
        ("description", description),
    ):
        if value is not None:
            attrib[key] = value

    data = {}
    for key, value in (
        ("host_name", host_name),
        ("version", version),
        ("comment", comment),
    ):
        if value is not None:
            data[key] = value

    workfile_info = {
        "id": uuid.uuid4().hex,
        "path": rootless_path,
        "taskId": task_id,
        "attrib": attrib,
        "data": data,
        # TODO remove 'createdBy' and 'updatedBy' fields when server is
        #   or above 1.1.3 .
        "createdBy": username,
        "updatedBy": username,
    }

    session = OperationsSession()
    session.create_entity(
        project_name, "workfile", workfile_info
    )
    session.commit()
    return workfile_info