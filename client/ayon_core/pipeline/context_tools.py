"""Core pipeline functionality"""
from __future__ import annotations

import os
import logging
import platform
import uuid
import warnings
from typing import Optional, Any

import ayon_api
import pyblish.api
from pyblish.lib import MessageHandler

from ayon_core import AYON_CORE_ROOT
from ayon_core.host import HostBase
from ayon_core.lib import (
    is_in_tests,
    initialize_ayon_connection,
)
from ayon_core.addon import load_addons, AddonsManager
from ayon_core.settings import get_project_settings

from .publish.lib import filter_pyblish_plugins
from .anatomy import Anatomy
from .template_data import get_template_data_with_names
from .workfile import get_custom_workfile_template_by_string_context
from . import (
    register_loader_plugin_path,
    register_inventory_action_path,
    register_creator_plugin_path,
    deregister_loader_plugin_path,
    deregister_inventory_action_path
)


_is_installed = False
_process_id = None
_registered_root = {"_": {}}
_registered_host = {"_": None}
# Keep modules manager (and it's modules) in memory
# - that gives option to register modules' callbacks
_addons_manager = None

log = logging.getLogger(__name__)

PLUGINS_DIR = os.path.join(AYON_CORE_ROOT, "plugins")

# Global plugin paths
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")


def _get_addons_manager():
    """Get or create modules manager for host installation.

    This is not meant for public usage. Reason is to keep modules
    in memory of process to be able trigger their event callbacks if they
    need any.

    Returns:
        AddonsManager: Manager wrapping discovered modules.
    """

    global _addons_manager
    if _addons_manager is None:
        _addons_manager = AddonsManager()
    return _addons_manager


def register_root(path):
    """DEPRECATED Register currently active root."""
    log.info("Registering root: %s" % path)
    _registered_root["_"] = path


def registered_root():
    """Return registered roots from current project anatomy.

    Consider this does return roots only for current project and current
        platforms, only if host was installer using 'install_host'.

    Deprecated:
        Please use project 'Anatomy' to get roots. This function is still used
            at current core functions of load logic, but that will change
            in future and this function will be removed eventually. Using this
            function at new places can cause problems in the future.

    Returns:
        dict[str, str]: Root paths.

    """
    warnings.warn(
        "Used deprecated function 'registered_root'. Please use 'Anatomy'"
        " to get roots.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _registered_root["_"]


def install_host(host: HostBase) -> None:
    """Install `host` into the running Python session.

    Args:
        host (HostBase): A host interface object.

    """
    if not isinstance(host, HostBase):
        log.error(
            f"Host must be a subclass of 'HostBase', got '{type(host)}'."
        )

    global _is_installed

    _is_installed = True

    # Make sure global AYON connection has set site id and version
    initialize_ayon_connection()

    addons_manager = _get_addons_manager()

    project_name = os.getenv("AYON_PROJECT_NAME")
    # WARNING: This might be an issue
    #   - commented out because 'traypublisher' does not have set project
    # if not project_name:
    #     raise ValueError(
    #         "AYON_PROJECT_NAME is missing in environment variables."
    #     )

    log.info("Activating {}..".format(project_name))

    # Optional host install function
    if hasattr(host, "install"):
        host.install()

    register_host(host)

    def modified_emit(obj, record):
        """Method replacing `emit` in Pyblish's MessageHandler."""
        try:
            record.msg = record.getMessage()
        except Exception:
            record.msg = str(record.msg)
        obj.records.append(record)

    MessageHandler.emit = modified_emit

    if os.environ.get("AYON_REMOTE_PUBLISH"):
        # target "farm" == rendering on farm, expects AYON_PUBLISH_DATA
        # target "remote" == remote execution, installs host
        print("Registering pyblish target: remote")
        pyblish.api.register_target("remote")
    else:
        pyblish.api.register_target("local")

    if is_in_tests():
        print("Registering pyblish target: automated")
        pyblish.api.register_target("automated")

    host_name = os.environ.get("AYON_HOST_NAME")

    # Give option to handle host installation
    for addon in addons_manager.get_enabled_addons():
        addon.on_host_install(host, host_name, project_name)

    install_ayon_plugins(project_name, host_name)


def install_ayon_plugins(project_name=None, host_name=None):
    """Install AYON core plugins and make sure the core is initialized.

    Args:
        project_name (Optional[str]): Name of project to install plugins for.
        host_name (Optional[str]): Name of host to install plugins for.

    """
    # Make sure global AYON connection has set site id and version
    # - this is necessary if 'install_host' is not called
    initialize_ayon_connection()
    # Make sure addons are loaded
    load_addons()

    log.info("Registering global plug-ins..")
    pyblish.api.register_plugin_path(PUBLISH_PATH)
    pyblish.api.register_discovery_filter(filter_pyblish_plugins)
    register_loader_plugin_path(LOAD_PATH)
    register_inventory_action_path(INVENTORY_PATH)

    if host_name is None:
        host_name = get_current_host_name()

    addons_manager = _get_addons_manager()
    publish_plugin_dirs = addons_manager.collect_publish_plugin_paths(
        host_name)
    for path in publish_plugin_dirs:
        pyblish.api.register_plugin_path(path)

    create_plugin_paths = addons_manager.collect_create_plugin_paths(
        host_name)
    for path in create_plugin_paths:
        register_creator_plugin_path(path)

    load_plugin_paths = addons_manager.collect_load_plugin_paths(
        host_name)
    for path in load_plugin_paths:
        register_loader_plugin_path(path)

    inventory_action_paths = addons_manager.collect_inventory_action_paths(
        host_name)
    for path in inventory_action_paths:
        register_inventory_action_path(path)

    if project_name is None:
        project_name = os.environ.get("AYON_PROJECT_NAME")

    # Register studio specific plugins
    if project_name:
        anatomy = Anatomy(project_name)
        anatomy.set_root_environments()
        register_root(anatomy.roots)

        project_settings = get_project_settings(project_name)
        platform_name = platform.system().lower()
        project_plugins = (
            project_settings
            ["core"]
            ["project_plugins"]
            .get(platform_name)
        ) or []
        for path in project_plugins:
            try:
                path = str(path.format(**os.environ))
            except KeyError:
                pass

            if not path or not os.path.exists(path):
                continue

            pyblish.api.register_plugin_path(path)
            register_loader_plugin_path(path)
            register_creator_plugin_path(path)
            register_inventory_action_path(path)


def uninstall_host():
    """Undo all of what `install()` did"""
    host = registered_host()

    try:
        host.uninstall()
    except AttributeError:
        pass

    log.info("Deregistering global plug-ins..")
    pyblish.api.deregister_plugin_path(PUBLISH_PATH)
    pyblish.api.deregister_discovery_filter(filter_pyblish_plugins)
    deregister_loader_plugin_path(LOAD_PATH)
    deregister_inventory_action_path(INVENTORY_PATH)
    log.info("Global plug-ins unregistered")

    deregister_host()

    log.info("Successfully uninstalled Avalon!")


def is_installed():
    """Return state of installation

    Returns:
        True if installed, False otherwise

    """

    return _is_installed


def register_host(host):
    """Register a new host for the current process

    Arguments:
        host (ModuleType): A module implementing the
            Host API interface. See the Host API
            documentation for details on what is
            required, or browse the source code.

    """

    _registered_host["_"] = host


def registered_host():
    """Return currently registered host"""
    return _registered_host["_"]


def deregister_host():
    _registered_host["_"] = None


def get_current_host_name():
    """Current host name.

    Function is based on currently registered host integration or environment
    variable 'AYON_HOST_NAME'.

    Returns:
        Union[str, None]: Name of host integration in current process or None.
    """

    host = registered_host()
    if isinstance(host, HostBase):
        return host.name
    return os.environ.get("AYON_HOST_NAME")


def get_global_context():
    """Global context defined in environment variables.

    Values here may not reflect current context of host integration. The
    function can be used on startup before a host is registered.

    Use 'get_current_context' to make sure you'll get current host integration
    context info.

    Example::

        {
            "project_name": "Commercial",
            "folder_path": "Bunny",
            "task_name": "Animation",
        }

    Returns:
        dict[str, Union[str, None]]: Context defined with environment
            variables.
    """

    return {
        "project_name": os.environ.get("AYON_PROJECT_NAME"),
        "folder_path": os.environ.get("AYON_FOLDER_PATH"),
        "task_name": os.environ.get("AYON_TASK_NAME"),
    }


def get_current_context():
    host = registered_host()
    if isinstance(host, HostBase):
        return host.get_current_context()
    return get_global_context()


def get_current_project_name():
    host = registered_host()
    if isinstance(host, HostBase):
        return host.get_current_project_name()
    return get_global_context()["project_name"]


def get_current_folder_path():
    host = registered_host()
    if isinstance(host, HostBase):
        return host.get_current_folder_path()
    return get_global_context()["folder_path"]


def get_current_task_name():
    host = registered_host()
    if isinstance(host, HostBase):
        return host.get_current_task_name()
    return get_global_context()["task_name"]


def get_current_project_settings() -> dict[str, Any]:
    """Project settings for the current context project.

    Returns:
        dict[str, Any]: Project settings for the current context project.

    Raises:
        ValueError: If current project is not set.

    """
    project_name = get_current_project_name()
    if not project_name:
        raise ValueError(
            "Current project is not set. Can't get project settings."
        )
    return get_project_settings(project_name)


def get_current_project_entity(fields=None):
    """Helper function to get project document based on global Session.

    This function should be called only in process where host is installed.

    Args:
        fields (Optional[Iterable[str]]): Limit returned data of project
            entity.

    Returns:
        Union[dict[str, Any], None]: Project entity of current project or None.

    """
    project_name = get_current_project_name()
    return ayon_api.get_project(project_name, fields=fields)


def get_current_folder_entity(fields=None):
    """Helper function to get folder entity based on current context.

    This function should be called only in process where host is installed.

    Folder is based on current context project name and folder path.

    Args:
        fields (Optional[Iterable[str]]): Limit returned data of folder entity
            to specific keys.

    Returns:
        Union[dict[str, Any], None]: Folder entity or None.

    """
    context = get_current_context()
    project_name = context["project_name"]
    folder_path = context["folder_path"]

    # Skip if is not set even on context
    if not project_name or not folder_path:
        return None
    return ayon_api.get_folder_by_path(
        project_name, folder_path, fields=fields
    )


def get_current_task_entity(fields=None):
    """Helper function to get task entity based on current context.

    This function should be called only in process where host is installed.

    Task is based on current context project name, folder path
        and task name.

    Args:
        fields (Optional[Iterable[str]]): Limit returned data of task entity
            to specific keys.

    Returns:
        Union[dict[str, Any], None]: Task entity or None.

    """
    context = get_current_context()
    project_name = context["project_name"]
    folder_path = context["folder_path"]
    task_name = context["task_name"]

    # Skip if is not set even on context
    if not project_name or not folder_path or not task_name:
        return None
    folder_entity = ayon_api.get_folder_by_path(
        project_name, folder_path, fields={"id"}
    )
    if not folder_entity:
        return None
    return ayon_api.get_task_by_name(
        project_name, folder_entity["id"], task_name, fields=fields
    )


def is_representation_from_latest(representation):
    """Return whether the representation is from latest version

    Args:
        representation (dict): The representation document from the database.

    Returns:
        bool: Whether the representation is of latest version.
    """

    project_name = get_current_project_name()
    return ayon_api.version_is_latest(
        project_name, representation["versionId"]
    )


def get_current_context_template_data(settings=None):
    """Prepare template data for current context.

    Args:
        settings (Optional[Dict[str, Any]]): Prepared studio or
            project settings.

    Returns:
        Dict[str, Any] Template data for current context.
    """

    context = get_current_context()
    project_name = context["project_name"]
    folder_path = context["folder_path"]
    task_name = context["task_name"]
    host_name = get_current_host_name()

    return get_template_data_with_names(
        project_name, folder_path, task_name, host_name, settings
    )


def get_current_context_custom_workfile_template(project_settings=None):
    """Filter and fill workfile template profiles by current context.

    This function can be used only inside host where current context is set.

    Args:
        project_settings (Optional[dict[str, Any]]): Project settings

    Returns:
        str: Path to template or None if none of profiles match current
            context. (Existence of formatted path is not validated.)

    """
    context = get_current_context()
    return get_custom_workfile_template_by_string_context(
        context["project_name"],
        context["folder_path"],
        context["task_name"],
        get_current_host_name(),
        project_settings=project_settings
    )


_PLACEHOLDER = object()


def change_current_context(
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    *,
    template_key: Optional[str] = _PLACEHOLDER,
    reason: Optional[str] = None,
    project_entity: Optional[dict[str, Any]] = None,
    anatomy: Optional[Anatomy] = None,
) -> dict[str, str]:
    """Update active Session to a new task work area.

    This updates the live Session to a different task under a folder.

    Notes:
        * This function does a lot of things related to workfiles which
            extends arguments options a lot.
        * We might want to implement 'set_current_context' on host integration
            instead. But `AYON_WORKDIR`, which is related to 'IWorkfileHost',
            would not be available in that case which might break some
            logic.

    Args:
        folder_entity (Dict[str, Any]): Folder entity to set.
        task_entity (Dict[str, Any]): Task entity to set.
        template_key (Optional[str]): DEPRECATED: Prepared template key to
            be used for workfile template in Anatomy.
        reason (Optional[str]): Reason for changing context.
        anatomy (Optional[Anatomy]): Anatomy object used for workdir
            calculation.
        project_entity (Optional[dict[str, Any]]): Project entity used for
            workdir calculation.

    Returns:
        dict[str, str]: New context data.

    """
    if template_key is not _PLACEHOLDER:
        warnings.warn(
            (
                "Used deprecated argument 'template_key' in"
                " 'change_current_context'."
                " It is not necessary to pass it in anymore."
            ),
            DeprecationWarning,
            stacklevel=2,
        )

    host = registered_host()
    return host.set_current_context(
        folder_entity,
        task_entity,
        reason=reason,
        project_entity=project_entity,
        anatomy=anatomy,
    )


def get_process_id():
    """Fake process id created on demand using uuid.

    Can be used to create process specific folders in temp directory.

    Returns:
        str: Process id.
    """

    global _process_id
    if _process_id is None:
        _process_id = str(uuid.uuid4())
    return _process_id


def version_up_current_workfile():
    """DEPRECATED Function to increment and save workfile.

    Please use 'save_next_version' from 'ayon_core.pipeline.workfile' instead.

    """
    warnings.warn(
        "Used deprecated 'version_up_current_workfile' please use"
        " 'save_next_version' from 'ayon_core.pipeline.workfile' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from ayon_core.pipeline.workfile import save_next_version
    save_next_version()
