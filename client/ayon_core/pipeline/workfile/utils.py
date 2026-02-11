from __future__ import annotations
import copy
import os
import platform
import shutil
import uuid
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.host.interfaces.workfiles import deprecated
from ayon_core.lib import filter_profiles, get_ayon_username, StringTemplate
from ayon_core.pipeline import get_representation_path
from ayon_core.settings import get_project_settings
from ayon_core.host.interfaces import (
    SaveWorkfileOptionalData,
    ListWorkfilesOptionalData,
    CopyWorkfileOptionalData,
)
from ayon_core.pipeline.version_start import get_versioning_start
from ayon_core.pipeline.template_data import get_template_data

from .path_resolving import (
    get_workdir,
    get_workfile_template_key,
    get_last_workfile_with_version,
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


class MissingWorkdirError(Exception):
    """Raised when accessing a work directory not found on disk."""
    pass


@dataclass
class LastPublishedWorkfileInfo:
    """Resolved info about the last published workfile."""

    source_path: str
    representation_entity: dict[str, Any]
    version_entity: dict[str, Any]
    extension: str  # e.g. "blend", no dot prefix


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
            workfile entities related to the task.

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


def get_workfile_on_launch_profile(
    project_name: str,
    host_name: str,
    task_name: str,
    task_type: str,
    project_settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Get matched last_workfile_on_startup profile for the context.

    Returns the profile dict with keys 'enabled' and
    'use_last_published_workfile', or None if no profile matches.

    Args:
        project_name (str): Name of project.
        host_name (str): Name of host which is launched. Not case sensitive.
        task_name (str): Name of task. Not case sensitive.
        task_type (str): Task type.
        project_settings (Optional[dict[str, Any]]): Project settings.

    Returns:
        Optional[dict[str, Any]]: Matched profile dict or None.
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
        return None
    filter_data = {
        "tasks": task_name,
        "task_types": task_type,
        "hosts": host_name,
    }
    return filter_profiles(profiles, filter_data)


@deprecated("Use get_workfile_on_launch_profile() instead.")
def should_use_last_workfile_on_launch(
    project_name: str,
    host_name: str,
    task_name: str,
    task_type: str,
    project_settings: Optional[dict[str, Any]] = None,
) -> bool:
    """Check if published workfile should be copied to workdir on launch.

    Backwards-compatible wrapper around get_workfile_on_launch_profile().
    Default output is False if no profile matches. Can be overridden with
    environment variable AYON_OPEN_LAST_WORKFILE.

    Args:
        project_name (str): Name of project.
        host_name (str): Name of launched host. Not case sensitive.
        task_name (str): Name of launched task.
            Not case sensitive.
        task_type (str): Type of launched task.
        project_settings (Optional[dict[str, Any]]): Project settings.

    Returns:
        bool: True if last published workfile should be copied to workdir
            before opening. None if no profile is found.
    """
    profile = get_workfile_on_launch_profile(
        project_name, host_name, task_name, task_type,
        project_settings=project_settings,
    )
    if profile is None:

        return False
    return profile.get("enabled", False)


def get_last_published_workfile_representation(
    project_name: str,
    folder_id: str,
    task_id: str,
    extensions: Optional[typing.Iterable[str]] = None,
    anatomy: Optional["Anatomy"] = None,
    project_settings: Optional[dict[str, Any]] = None,
) -> Optional[LastPublishedWorkfileInfo]:
    """Resolve info about the latest published workfile for the context.

    Returns data needed to copy the file, or None if none found or accessible.

    Args:
        project_name (str): Project name.
        folder_id (str): Folder id.
        task_id (str): Task id (used to filter published versions).
        extensions (Optional[Iterable[str]]): Allowed workfile extensions.
            If None, first representation with an existing path is used.
        anatomy (Optional[Anatomy]): Project anatomy. Resolved from
            project_name if not provided.
        project_settings (Optional[dict[str, Any]]): Project settings.
            Resolved from project_name if not provided.

    Returns:
        Optional[LastPublishedWorkfileInfo]: Resolved info, or None.
    """
    if anatomy is None:
        from ayon_core.pipeline import Anatomy
        anatomy = Anatomy(project_name)
    if project_settings is None:
        project_settings = get_project_settings(project_name)

    ext_set = None
    if extensions:
        ext_set = {str(ext).lstrip(".").lower() for ext in extensions}

    product_entities = list(
        ayon_api.get_products(
            project_name,
            folder_ids={folder_id},
            product_types={"workfile"},
            fields={"id", "name"},
        )
    )
    if not product_entities:
        return None

    latest_version = next(
        ayon_api.get_versions(
            project_name,
            product_ids={p["id"] for p in product_entities},
            task_ids={task_id},
            latest=True,
            standard=True,
            fields={"id", "author", "version", "taskId"},
        )
    )

    repre_entities = list(
        ayon_api.get_representations(
            project_name,
            version_ids={latest_version["id"]},
        )
    )
    if not repre_entities:
        return None

    for repre in repre_entities:
        representation_path = Path(get_representation_path(
            project_name,
            repre,
            anatomy=anatomy,
        ))
        if not representation_path.exists():
            continue

        ext = representation_path.suffix.lower().lstrip(".")
        if ext_set is not None and ext in ext_set:
            return LastPublishedWorkfileInfo(
                source_path=representation_path.as_posix(),
                representation_entity=repre,
                version_entity=latest_version,
                extension=ext,
            )

    return None


def copy_last_published_workfile(
    project_name: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
    published_info: LastPublishedWorkfileInfo,
    workdir: Optional[str] = None,
    file_template: Optional[str] = None,
    workdir_data: Optional[dict[str, Any]] = None,
    anatomy: Optional["Anatomy"] = None,
    project_settings: Optional[dict[str, Any]] = None,
    log: Optional[Any] = None,
) -> Optional[str]:
    """Copy the published workfile to the work directory.

    Compares with latest local workfile; copies only if none exist or published
    is newer.

    Args:
        project_name (str): Project name.
        folder_entity (dict[str, Any]): Folder entity.
        task_entity (dict[str, Any]): Task entity.
        host_name (str): Host name.
        published_info (LastPublishedWorkfileInfo): From
            get_last_published_workfile_representation().
        workdir (Optional[str]): Work directory.
            Resolved from context if None.
        file_template (Optional[str]): Workfile filename template.
            Resolved if None.
        workdir_data (Optional[dict[str, Any]]): Template data.
            Resolved if None.
            Not mutated.
        anatomy (Optional[Anatomy]): Project anatomy. Resolved if None.
        project_settings (Optional[dict[str, Any]]): Project settings.
            Resolved from project_name if None.
        log (Optional[Any]): Logger with debug/info/warning. No-op if None.

    Returns:
        Optional[str]: Path to the copied workfile, or None if copy skipped.
    """
    if anatomy is None:
        from ayon_core.pipeline import Anatomy
        anatomy = Anatomy(project_name)
    if project_settings is None:
        project_settings = get_project_settings(project_name)

    if workdir is None or file_template is None or workdir_data is None:
        project_entity = ayon_api.get_project(project_name)
        if workdir_data is None:
            workdir_data = get_template_data(
                project_entity,
                folder_entity,
                task_entity,
                host_name,
                project_settings,
            )
        template_key = get_workfile_template_key(
            project_name,
            task_entity["taskType"],
            host_name,
            project_settings=project_settings,
        )
        if file_template is None:
            file_template = anatomy.get_template_item(
                "work", template_key, "file"
            ).template
        if workdir is None:
            workdir_result = get_workdir(
                project_entity,
                folder_entity,
                task_entity,
                host_name,
                anatomy=anatomy,
                template_key=template_key,
                project_settings=project_settings,
            )
            workdir = str(workdir_result)

    # Use a copy for template filling; do not mutate callers' workdir_data
    template_data = copy.deepcopy(workdir_data)
    template_data["ext"] = published_info.extension
    ext_set = {published_info.extension}

    local_path, local_version = get_last_workfile_with_version(
        workdir,
        file_template,
        template_data,
        ext_set,
    )

    published_version = published_info.version_entity.get("version", 0)

    if local_version is None:
        # No local workfiles: use latest published version + 1
        next_version = published_version + 1
    else:
        published_mtime = os.path.getmtime(published_info.source_path)
        local_mtime = (
            os.path.getmtime(local_path) if os.path.exists(local_path) else 0
        )
        if published_mtime <= local_mtime:
            if log:
                log.debug(
                    "Latest local workfile is newer than last published; "
                    "skipping copy."
                )
            return None

        # Use the greater of local or published version, then + 1
        next_version = max(local_version, published_version) + 1

    data = copy.deepcopy(template_data)
    data["version"] = next_version
    data.pop("comment", None)
    data["ext"] = published_info.extension
    filename = StringTemplate.format_strict_template(file_template, data)
    dst_path = Path(workdir) / str(filename)
    dst_path = dst_path.resolve()

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(published_info.source_path, dst_path)

    rootless_path = find_workfile_rootless_path(
        str(dst_path),
        project_name,
        folder_entity,
        task_entity,
        host_name,
        project_settings=project_settings,
        anatomy=anatomy,
    )
    save_workfile_info(
        project_name,
        task_entity["id"],
        rootless_path,
        host_name,
        version=next_version,
        comment=None,
        description=None,
    )

    if log:
        log.info(
            f"Copied last published workfile to {dst_path} "
            f"(version {next_version})",
        )
    return dst_path.as_posix()


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
    data: Optional[dict[str, Any]] = None,
    workfile_entities: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Save workfile info entity for a workfile path.

    Args:
        project_name (str): The name of the project.
        task_id (str): Task id under which is workfile created.
        rootless_path (str): Rootless path of the workfile.
        host_name (str): Name of host which is saving the workfile.
        version (Optional[int]): Workfile version.
        comment (Optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        username (Optional[str]): Username of user who saves the workfile.
            If not provided, current user is used.
        data (Optional[dict[str, Any]]): Additional workfile entity data.
        workfile_entities (Optional[list[dict[str, Any]]]): Pre-fetched
            workfile entities related to task.

    Returns:
        dict[str, Any]: Workfile info entity.

    """
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

    attrib = {}
    extension = os.path.splitext(rootless_path)[1]
    for key, value in (
        ("extension", extension),
        ("description", description),
    ):
        if value is not None:
            attrib[key] = value

    if data is None:
        data = {}

    if not workfile_entity:
        return _create_workfile_info_entity(
            project_name,
            task_id,
            host_name,
            rootless_path,
            username,
            version,
            comment,
            attrib,
            data,
        )

    for key, value in (
        ("host_name", host_name),
        ("version", version),
        ("comment", comment),
    ):
        if value is not None:
            data[key] = value

    changed_data = {}
    old_data = workfile_entity["data"]
    for key, value in data.items():
        if key not in old_data or old_data[key] != value:
            changed_data[key] = value
            workfile_entity["data"][key] = value

    changed_attrib = {}
    old_attrib = workfile_entity["attrib"]
    for key, value in attrib.items():
        if key not in old_attrib or old_attrib[key] != value:
            changed_attrib[key] = value
            workfile_entity["attrib"][key] = value

    update_data = {}
    if changed_data:
        update_data["data"] = changed_data

    if changed_attrib:
        update_data["attrib"] = changed_attrib

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
        return workfile_entity

    session = OperationsSession()
    session.update_entity(
        project_name,
        "workfile",
        workfile_entity["id"],
        update_data,
    )
    session.commit()
    return workfile_entity


def save_current_workfile_to(
    workfile_path: str,
    folder_path: str,
    task_name: str,
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    prepared_data: Optional[SaveWorkfileOptionalData] = None,
) -> None:
    """Save current workfile to new location or context.

    Args:
        workfile_path (str): Destination workfile path.
        folder_path (str): Target folder path.
        task_name (str): Target task name.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        prepared_data (Optional[SaveWorkfileOptionalData]): Prepared data
            for speed enhancements.

    """
    from ayon_core.pipeline.context_tools import registered_host

    host = registered_host()
    context = host.get_current_context()
    project_name = context["project_name"]
    folder_entity = ayon_api.get_folder_by_path(
        project_name, folder_path
    )
    task_entity = ayon_api.get_task_by_name(
        project_name, folder_entity["id"], task_name
    )
    host.save_workfile_with_context(
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        prepared_data=prepared_data,
    )


def save_workfile_with_current_context(
    workfile_path: str,
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    prepared_data: Optional[SaveWorkfileOptionalData] = None,
) -> None:
    """Save current workfile to new location using current context.

    Helper function to save workfile using current context. Calls
        'save_current_workfile_to' at the end.

    Args:
        workfile_path (str): Destination workfile path.
        version (Optional[int]): Workfile version.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        prepared_data (Optional[SaveWorkfileOptionalData]): Prepared data
            for speed enhancements.

    """
    from ayon_core.pipeline.context_tools import registered_host

    host = registered_host()
    context = host.get_current_context()
    project_name = context["project_name"]
    folder_path = context["folder_path"]
    task_name = context["task_name"]
    folder_entity = task_entity = None
    if folder_path:
        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if folder_entity and task_name:
            task_entity = ayon_api.get_task_by_name(
                project_name, folder_entity["id"], task_name
            )

    host.save_workfile_with_context(
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        prepared_data=prepared_data,
    )


def save_next_version(
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    *,
    prepared_data: Optional[SaveWorkfileOptionalData] = None,
) -> None:
    """Save workfile using current context, version and comment.

    Helper function to save a workfile using the current context. Last
        workfile version + 1 is used if is not passed in.

    Args:
        version (Optional[int]): Workfile version that will be used. Last
            version + 1 is used if is not passed in.
        comment (optional[str]): Workfile comment. Pass '""' to clear comment.
            The current workfile comment is used if it is not passed.
        description (Optional[str]): Workfile description.
        prepared_data (Optional[SaveWorkfileOptionalData]): Prepared data
            for speed enhancements.

    """
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.context_tools import registered_host

    host = registered_host()
    current_path = host.get_current_workfile()
    if not current_path:
        current_path = None
    else:
        current_path = os.path.normpath(current_path)

    context = host.get_current_context()
    project_name = context["project_name"]
    folder_path = context["folder_path"]
    task_name = context["task_name"]
    if prepared_data is None:
        prepared_data = SaveWorkfileOptionalData()

    project_entity = prepared_data.project_entity
    anatomy = prepared_data.anatomy
    project_settings = prepared_data.project_settings

    if project_entity is None:
        project_entity = ayon_api.get_project(project_name)
        prepared_data.project_entity = project_entity

    if project_settings is None:
        project_settings = get_project_settings(project_name)
        prepared_data.project_settings = project_settings

    if anatomy is None:
        anatomy = Anatomy(project_name, project_entity=project_entity)
        prepared_data.anatomy = anatomy

    folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
    task_entity = ayon_api.get_task_by_name(
        project_name, folder_entity["id"], task_name
    )

    template_key = get_workfile_template_key(
        project_name,
        task_entity["taskType"],
        host.name,
        project_settings=project_settings
    )
    file_template = anatomy.get_template_item("work", template_key, "file")
    template_data = get_template_data(
        project_entity,
        folder_entity,
        task_entity,
        host.name,
        project_settings,
    )
    workdir = get_workdir(
        project_entity,
        folder_entity,
        task_entity,
        host.name,
        anatomy=anatomy,
        template_key=template_key,
        project_settings=project_settings,
    )
    rootless_dir = workdir.rootless
    last_workfile = None
    current_workfile = None
    if version is None or comment is None:
        workfiles = host.list_workfiles(
            project_name, folder_entity, task_entity,
            prepared_data=ListWorkfilesOptionalData(
                project_entity=project_entity,
                anatomy=anatomy,
                project_settings=project_settings,
                template_key=template_key,
            )
        )
        for workfile in workfiles:
            if current_workfile is None and workfile.filepath == current_path:
                current_workfile = workfile

            if workfile.version is None:
                continue

            if (
                last_workfile is None
                or last_workfile.version < workfile.version
            ):
                last_workfile = workfile

    if version is None and last_workfile is not None:
        version = last_workfile.version + 1

    if version is None:
        version = get_versioning_start(
            project_name,
            host.name,
            task_name=task_entity["name"],
            task_type=task_entity["taskType"],
            product_base_type="workfile",
        )

    # Re-use comment from the current workfile if is not passed in
    if comment is None and current_workfile is not None:
        comment = current_workfile.comment

    template_data["version"] = version
    if comment:
        template_data["comment"] = comment

    # Resolve extension
    # - Don't fill any if the host does not have defined any -> e.g. if host
    #   uses directory instead of a file.
    # 1. Use the current file extension.
    # 2. Use the last known workfile extension.
    # 3. Use the first extensions from 'get_workfile_extensions'.
    ext = None
    workfile_extensions = host.get_workfile_extensions()
    if workfile_extensions:
        if current_path:
            ext = os.path.splitext(current_path)[1]
        elif last_workfile is not None:
            ext = os.path.splitext(last_workfile.filepath)[1]
        else:
            ext = next(iter(workfile_extensions))
        ext = ext.lstrip(".")

    if ext:
        template_data["ext"] = ext

    filename = file_template.format_strict(template_data)
    workfile_path = os.path.join(workdir, filename)
    rootless_path = f"{rootless_dir}/{filename}"
    if platform.system().lower() == "windows":
        rootless_path = rootless_path.replace("\\", "/")
    prepared_data.rootless_path = rootless_path

    host.save_workfile_with_context(
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        prepared_data=prepared_data,
    )


def copy_workfile_to_context(
    src_workfile_path: str,
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    version: Optional[int] = None,
    comment: Optional[str] = None,
    description: Optional[str] = None,
    open_workfile: bool = True,
    prepared_data: Optional[CopyWorkfileOptionalData] = None,
) -> None:
    """Copy workfile to a context.

    Copy workfile to a specified folder and task. Destination path is
        calculated based on passed information.

    Args:
        src_workfile_path (str): Source workfile path.
        folder_entity (dict[str, Any]): Target folder entity.
        task_entity (dict[str, Any]): Target task entity.
        version (Optional[int]): Workfile version. Use next version if not
            passed.
        comment (optional[str]): Workfile comment.
        description (Optional[str]): Workfile description.
        prepared_data (Optional[CopyWorkfileOptionalData]): Prepared data
            for speed enhancements. Rootless path is calculated in this
            function.

    """
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.context_tools import registered_host

    host = registered_host()
    project_name = host.get_current_project_name()

    anatomy = prepared_data.anatomy
    if anatomy is None:
        if prepared_data.project_entity is None:
            prepared_data.project_entity = ayon_api.get_project(
                project_name
            )
        anatomy = Anatomy(
            project_name, project_entity=prepared_data.project_entity
        )
        prepared_data.anatomy = anatomy

    project_settings = prepared_data.project_settings
    if project_settings is None:
        project_settings = get_project_settings(project_name)
        prepared_data.project_settings = project_settings

    if version is None:
        list_prepared_data = None
        if prepared_data is not None:
            list_prepared_data = ListWorkfilesOptionalData(
                project_entity=prepared_data.project_entity,
                anatomy=prepared_data.anatomy,
                project_settings=prepared_data.project_settings,
                workfile_entities=prepared_data.workfile_entities,
            )

        workfiles = host.list_workfiles(
            project_name,
            folder_entity,
            task_entity,
            prepared_data=list_prepared_data
        )
        if workfiles:
            version = max(
                workfile.version
                for workfile in workfiles
            ) + 1
        else:
            version = get_versioning_start(
                project_name,
                host.name,
                task_name=task_entity["name"],
                task_type=task_entity["taskType"],
                product_base_type="workfile",
            )

    task_type = task_entity["taskType"]
    template_key = get_workfile_template_key(
        project_name,
        task_type,
        host.name,
        project_settings=prepared_data.project_settings
    )

    template_data = get_template_data(
        prepared_data.project_entity,
        folder_entity,
        task_entity,
        host.name,
        prepared_data.project_settings,
    )
    template_data["version"] = version
    if comment:
        template_data["comment"] = comment

    workfile_extensions = host.get_workfile_extensions()
    if workfile_extensions:
        ext = os.path.splitext(src_workfile_path)[1].lstrip(".")
        template_data["ext"] = ext

    workfile_template = anatomy.get_template_item(
        "work", template_key, "path"
    )
    workfile_path = workfile_template.format_strict(template_data)
    prepared_data.rootless_path = workfile_path.rootless
    host.copy_workfile(
        src_workfile_path,
        workfile_path,
        folder_entity,
        task_entity,
        version=version,
        comment=comment,
        description=description,
        open_workfile=open_workfile,
        prepared_data=prepared_data,
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
    attrib: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create workfile entity data.

    Args:
        project_name (str): Project name.
        task_id (str): Task id.
        host_name (str): Host name.
        rootless_path (str): Rootless workfile path.
        username (str): Username.
        version (Optional[int]): Workfile version.
        comment (Optional[str]): Workfile comment.
        attrib (dict[str, Any]): Workfile entity attributes.
        data (dict[str, Any]): Workfile entity data.

    Returns:
        dict[str, Any]: Created workfile entity data.

    """
    data.update({
        "host_name": host_name,
        "version": version,
        "comment": comment,
    })

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
