from .path_resolving import (
    get_workfile_template_key_from_context,
    get_workfile_template_key,
    get_workdir_with_workdir_data,
    get_workdir,

    get_last_workfile_with_version,
    get_last_workfile,

    get_custom_workfile_template,
    get_custom_workfile_template_by_string_context,

    create_workdir_extra_folders,
)

from .utils import (
    should_use_last_workfile_on_launch,
    should_open_workfiles_tool_on_launch,
)

from .build_workfile import BuildWorkfile


from .workfile_template_builder import (
    discover_template_placeholder_plugins,
    register_template_placeholder_plugin,
    deregister_template_placeholder_plugin,
    register_template_placeholder_plugin_path,
    deregister_template_placeholder_plugin_path,
)


__all__ = (
    "get_workfile_template_key_from_context",
    "get_workfile_template_key",
    "get_workdir_with_workdir_data",
    "get_workdir",

    "get_last_workfile_with_version",
    "get_last_workfile",

    "get_custom_workfile_template",
    "get_custom_workfile_template_by_string_context",

    "create_workdir_extra_folders",

    "should_use_last_workfile_on_launch",
    "should_open_workfiles_tool_on_launch",

    "BuildWorkfile",

    "discover_template_placeholder_plugins",
    "register_template_placeholder_plugin",
    "deregister_template_placeholder_plugin",
    "register_template_placeholder_plugin_path",
    "deregister_template_placeholder_plugin_path",
)
