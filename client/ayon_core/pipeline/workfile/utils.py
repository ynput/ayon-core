from __future__ import annotations
import os
import platform
import uuid
import typing
from typing import Optional, Any

import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import filter_profiles, get_ayon_username
from ayon_core.settings import get_project_settings

from .path_resolving import get_workfile_template_key

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class MissingWorkdirError(Exception):
    """Raised when accessing a work directory not found on disk."""
    pass


def get_workfiles_info(
    workfile_path: str,
    project_name: str,
    task_id: str,
    *,
    anatomy: Optional["Anatomy"] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """Find workfile info entity for a workfile path.

    Args:
        workfile_path (str): Workfile path.
        project_name (str): The name of the project.
        task_id (str): Task id under which is workfile created.
        anatomy (Optional[Anatomy]): Project anatomy used to get roots.
        workfile_entities (Optional[list[dict[str, Any]]]): Pre-fetched
            workfile entities related to task.

    Returns:
        Optional[dict[str, Any]]: Workfile info entity if found, otherwise
            `None`.

    """
    if anatomy is None:
        anatomy = Anatomy(project_name)

    if workfile_entities is None:
        workfile_entities = list(ayon_api.get_workfiles_info(
            project_name,
            task_ids=[task_id],
        ))

    if platform.system().lower() == "windows":
        workfile_path = workfile_path.replace("\\", "/")
    workfile_path = workfile_path.lower()

    for workfile_entity in workfile_entities:
        path = workfile_entity["path"]
        filled_path = anatomy.fill_root(path)
        if platform.system().lower() == "windows":
            filled_path = filled_path.replace("\\", "/")
        filled_path = filled_path.lower()
        if filled_path == workfile_path:
            return workfile_entity
    return None


def should_use_last_workfile_on_launch(
    project_name: str,
    host_name: str,
    task_name: str,
    task_type: str,
    default_output: bool = False,
    project_settings: Optional[dict[str, Any]] = None,
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


def save_workfile_info(
    project_name: str,
    task_id: str,
    rootless_path: str,
    host_name: str,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    username: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
):
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
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
):
    from ayon_core.pipeline.context_tools import registered_host

    # Trigger before save event
    host = registered_host()
    host.open_workfile_with_context(
        filepath,
        folder_entity,
        task_entity,
        project_entity=project_entity,
        project_settings=project_settings,
        anatomy=anatomy,
    )


def save_current_workfile_to(
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    rootless_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
):
    """Save current workfile to new location or context.

    Args:
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
            entities related to task.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    from ayon_core.pipeline.context_tools import registered_host

    # Trigger before save event
    host = registered_host()
    host.save_workfile_with_context(
        workfile_path,
        folder_entity,
        task_entity,
        version,
        comment,
        description,
        rootless_path=rootless_path,
        workfile_entities=workfile_entities,
        project_entity=project_entity,
        project_settings=project_settings,
        anatomy=anatomy,
    )


def copy_and_open_workfile(
    src_workfile_path: str,
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    rootless_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
):
    """Copy workfile to new location and open it.

    Args:
        src_workfile_path (str): Source workfile path.
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    from ayon_core.pipeline.context_tools import registered_host

    host = registered_host()
    host.copy_workfile(
        src_workfile_path,
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        rootless_path=rootless_path,
        workfile_entities=workfile_entities,
        project_entity=project_entity,
        project_settings=project_settings,
        anatomy=anatomy,
        open_workfile=True,
    )


def copy_and_open_workfile_representation(
    src_project_name: str,
    representation_id: str,
    workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    rootless_path: Optional[str] = None,
    representation_entity: Optional[dict[str, Any]] = None,
    representation_path: Optional[str] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
    src_anatomy: Optional["Anatomy"] = None,
):
    """Copy workfile to new location and open it.

    Args:
        src_project_name (str): Project name where representation is stored.
        representation_id (str): Source representation id.
        workfile_path (str): Destination workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        rootless_path (Optional[str]): Rootless path of the workfile. Is
            calculated if not passed in.
        representation_entity (Optional[dict[str, Any]]): Representation
            entity. If not provided, it will be fetched from the server.
        representation_path (Optional[str]): Path to the representation.
            Calculated if not provided.
        workfile_entities (Optional[list[dict[str, Any]]]): List of workfile
        project_entity (Optional[dict[str, Any]]): Project entity used for
            rootless path calculation.
        project_settings (Optional[dict[str, Any]]): Project settings used for
            rootless path calculation.
        anatomy (Optional[Anatomy]): Project anatomy used for rootless
            path calculation.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
    from ayon_core.pipeline.context_tools import registered_host

    if representation_entity is None:
        representation_entity = ayon_api.get_representation_by_id(
            src_project_name,
            representation_id,
        )

    host = registered_host()
    host.copy_workfile_representation(
        src_project_name,
        representation_entity,
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        rootless_path=rootless_path,
        workfile_entities=workfile_entities,
        project_settings=project_settings,
        project_entity=project_entity,
        anatomy=anatomy,
        src_anatomy=src_anatomy,
        src_representation_path=representation_path,
        open_workfile=open_workfile,
    )


def find_workfile_rootless_path(
    workfile_path: str,
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
    *,
    project_entity: Optional[dict[str, Any]] = None,
    project_settings: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
) -> str:
    """Find rootless workfile path."""
    if anatomy is None:
        from ayon_core.pipeline import Anatomy

        anatomy = Anatomy(project_name, project_entity=project_entity)

    task_type = task_entity["taskType"]
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

    data = {
        key: value
        for key, value in (
            ("host_name", host_name),
            ("version", version),
            ("comment", comment),
        )
        if value is not None
    }

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
