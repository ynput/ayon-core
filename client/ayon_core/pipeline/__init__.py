from .constants import (
    AVALON_CONTAINER_ID,
    AVALON_INSTANCE_ID,
    AYON_CONTAINER_ID,
    AYON_INSTANCE_ID,
    HOST_WORKFILE_EXTENSIONS,
)

from .anatomy import Anatomy

from .create import (
    BaseCreator,
    Creator,
    AutoCreator,
    HiddenCreator,
    CreatedInstance,
    CreatorError,

    LegacyCreator,
    legacy_create,

    discover_creator_plugins,
    discover_legacy_creator_plugins,
    register_creator_plugin,
    deregister_creator_plugin,
    register_creator_plugin_path,
    deregister_creator_plugin_path,
)

from .load import (
    HeroVersionType,
    IncompatibleLoaderError,
    LoaderPlugin,
    ProductLoaderPlugin,

    discover_loader_plugins,
    register_loader_plugin,
    deregister_loader_plugin_path,
    register_loader_plugin_path,
    deregister_loader_plugin,

    load_container,
    remove_container,
    update_container,
    switch_container,

    loaders_from_representation,
    get_representation_path,
    get_representation_context,
    get_repres_contexts,
)

from .publish import (
    PublishValidationError,
    PublishXmlValidationError,
    KnownPublishError,
    AYONPyblishPluginMixin,
    OpenPypePyblishPluginMixin,
    OptionalPyblishPluginMixin,
)

from .actions import (
    LauncherAction,

    InventoryAction,

    discover_launcher_actions,
    register_launcher_action,
    register_launcher_action_path,

    discover_inventory_actions,
    register_inventory_action,
    register_inventory_action_path,
    deregister_inventory_action,
    deregister_inventory_action_path,
)

from .context_tools import (
    install_ayon_plugins,
    install_openpype_plugins,
    install_host,
    uninstall_host,
    is_installed,

    register_root,
    registered_root,

    register_host,
    registered_host,
    deregister_host,
    get_process_id,

    get_global_context,
    get_current_context,
    get_current_host_name,
    get_current_project_name,
    get_current_folder_path,
    get_current_task_name
)

from .workfile import (
    discover_workfile_build_plugins,
    register_workfile_build_plugin,
    deregister_workfile_build_plugin,
    register_workfile_build_plugin_path,
    deregister_workfile_build_plugin_path,
)

install = install_host
uninstall = uninstall_host


__all__ = (
    "AVALON_CONTAINER_ID",
    "AVALON_INSTANCE_ID",
    "AYON_CONTAINER_ID",
    "AYON_INSTANCE_ID",
    "HOST_WORKFILE_EXTENSIONS",

    # --- Anatomy ---
    "Anatomy",

    # --- Create ---
    "BaseCreator",
    "Creator",
    "AutoCreator",
    "HiddenCreator",
    "CreatedInstance",
    "CreatorError",

    "CreatorError",

    # - legacy creation
    "LegacyCreator",
    "legacy_create",

    "discover_creator_plugins",
    "discover_legacy_creator_plugins",
    "register_creator_plugin",
    "deregister_creator_plugin",
    "register_creator_plugin_path",
    "deregister_creator_plugin_path",

    # --- Load ---
    "HeroVersionType",
    "IncompatibleLoaderError",
    "LoaderPlugin",
    "ProductLoaderPlugin",

    "discover_loader_plugins",
    "register_loader_plugin",
    "deregister_loader_plugin_path",
    "register_loader_plugin_path",
    "deregister_loader_plugin",

    "load_container",
    "remove_container",
    "update_container",
    "switch_container",

    "loaders_from_representation",
    "get_representation_path",
    "get_representation_context",
    "get_repres_contexts",

    # --- Publish ---
    "PublishValidationError",
    "PublishXmlValidationError",
    "KnownPublishError",
    "AYONPyblishPluginMixin",
    "OpenPypePyblishPluginMixin",
    "OptionalPyblishPluginMixin",

    # --- Actions ---
    "LauncherAction",
    "InventoryAction",

    "discover_launcher_actions",
    "register_launcher_action",
    "register_launcher_action_path",

    "discover_inventory_actions",
    "register_inventory_action",
    "register_inventory_action_path",
    "deregister_inventory_action",
    "deregister_inventory_action_path",

    # --- Process context ---
    "install_ayon_plugins",
    "install_openpype_plugins",
    "install_host",
    "uninstall_host",
    "is_installed",

    "register_root",
    "registered_root",

    "register_host",
    "registered_host",
    "deregister_host",
    "get_process_id",

    "get_global_context",
    "get_current_context",
    "get_current_host_name",
    "get_current_project_name",
    "get_current_folder_path",
    "get_current_task_name",

    # Workfile templates
    "discover_workfile_build_plugins",
    "register_workfile_build_plugin",
    "deregister_workfile_build_plugin",
    "register_workfile_build_plugin_path",
    "deregister_workfile_build_plugin_path",

    # Backwards compatible function names
    "install",
    "uninstall",
)
