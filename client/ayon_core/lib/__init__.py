# -*- coding: utf-8 -*-
# flake8: noqa E402
"""AYON lib functions."""

from .local_settings import (
    IniSettingRegistry,
    JSONSettingRegistry,
    AYONSecureRegistry,
    AYONSettingsRegistry,
    get_launcher_local_dir,
    get_launcher_storage_dir,
    get_addons_resources_dir,
    get_local_site_id,
    get_ayon_user_entity,
    get_ayon_username,
)
from .ayon_connection import initialize_ayon_connection
from .cache import (
    CacheItem,
    NestedCacheItem,
)
from .track_changes import TrackDictChangesItem
from .events import (
    emit_event,
    register_event_callback
)

from .vendor_bin_utils import (
    ToolNotFoundError,
    find_executable,
    get_oiio_tools_path,
    get_oiio_tool_args,
    get_ffmpeg_tool_path,
    get_ffmpeg_tool_args,
    is_oiio_supported,
)

from .attribute_definitions import (
    AbstractAttrDef,

    UIDef,
    UISeparatorDef,
    UILabelDef,

    UnknownDef,
    NumberDef,
    TextDef,
    EnumDef,
    BoolDef,
    FileDef,
    FileDefItem,
)

from .env_tools import (
    compute_env_variables_structure,
    env_value_to_bool,
    get_paths_from_environ,
    merge_env_variables,
)

from .terminal import Terminal
from .execute import (
    get_ayon_launcher_args,
    get_linux_launcher_args,
    execute,
    run_subprocess,
    run_detached_process,
    run_ayon_launcher_process,
    run_detached_ayon_launcher_process,
    path_to_subprocess_arg,
    CREATE_NO_WINDOW
)
from .log import (
    Logger,
)

from .path_templates import (
    DefaultKeysDict,
    TemplateUnsolved,
    StringTemplate,
    FormatObject,
)

from .dateutils import (
    get_datetime_data,
    get_timestamp,
    get_formatted_current_time
)

from .python_module_tools import (
    import_filepath,
    modules_from_path,
    recursive_bases_from_class,
    classes_from_module,
    import_module_from_dirpath,
    is_func_signature_supported,
)

from .profiles_filtering import (
    compile_list_of_regexes,
    filter_profiles
)

from .transcoding import (
    get_transcode_temp_directory,
    should_convert_for_ffmpeg,
    convert_input_paths_for_ffmpeg,
    get_ffprobe_data,
    get_ffprobe_streams,
    get_ffmpeg_codec_args,
    get_ffmpeg_format_args,
    convert_ffprobe_fps_value,
    convert_ffprobe_fps_to_float,
    get_rescaled_command_arguments,
    get_media_mime_type,
)

from .plugin_tools import (
    prepare_template_data,
    source_hash,
)

from .path_tools import (
    format_file_size,
    collect_frames,
    create_hard_link,
    version_up,
    get_version_from_path,
    get_last_version_from_path,
)

from .ayon_info import (
    is_in_ayon_launcher_process,
    is_running_from_build,
    is_using_ayon_console,
    is_headless_mode_enabled,
    is_staging_enabled,
    is_dev_mode_enabled,
    is_in_tests,
    get_settings_variant,
)

terminal = Terminal

__all__ = [
    "IniSettingRegistry",
    "JSONSettingRegistry",
    "AYONSecureRegistry",
    "AYONSettingsRegistry",
    "get_launcher_local_dir",
    "get_launcher_storage_dir",
    "get_addons_resources_dir",
    "get_local_site_id",
    "get_ayon_user_entity",
    "get_ayon_username",

    "initialize_ayon_connection",

    "CacheItem",
    "NestedCacheItem",

    "TrackDictChangesItem",

    "emit_event",
    "register_event_callback",

    "get_ayon_launcher_args",
    "get_linux_launcher_args",
    "execute",
    "run_subprocess",
    "run_detached_process",
    "run_ayon_launcher_process",
    "run_detached_ayon_launcher_process",
    "path_to_subprocess_arg",
    "CREATE_NO_WINDOW",

    "compute_env_variables_structure",
    "env_value_to_bool",
    "get_paths_from_environ",
    "merge_env_variables",

    "ToolNotFoundError",
    "find_executable",
    "get_oiio_tools_path",
    "get_oiio_tool_args",
    "get_ffmpeg_tool_path",
    "get_ffmpeg_tool_args",
    "is_oiio_supported",

    "AbstractAttrDef",

    "UIDef",
    "UISeparatorDef",
    "UILabelDef",

    "UnknownDef",
    "NumberDef",
    "TextDef",
    "EnumDef",
    "BoolDef",
    "FileDef",
    "FileDefItem",

    "import_filepath",
    "modules_from_path",
    "recursive_bases_from_class",
    "classes_from_module",
    "import_module_from_dirpath",
    "is_func_signature_supported",

    "get_transcode_temp_directory",
    "should_convert_for_ffmpeg",
    "convert_input_paths_for_ffmpeg",
    "get_ffprobe_data",
    "get_ffprobe_streams",
    "get_ffmpeg_codec_args",
    "get_ffmpeg_format_args",
    "convert_ffprobe_fps_value",
    "convert_ffprobe_fps_to_float",
    "get_rescaled_command_arguments",
    "get_media_mime_type",

    "compile_list_of_regexes",

    "filter_profiles",

    "prepare_template_data",
    "source_hash",

    "format_file_size",
    "collect_frames",
    "create_hard_link",
    "version_up",
    "get_version_from_path",
    "get_last_version_from_path",

    "DefaultKeysDict",
    "TemplateUnsolved",
    "StringTemplate",
    "FormatObject",

    "terminal",

    "get_datetime_data",
    "get_timestamp",
    "get_formatted_current_time",

    "Logger",

    "is_in_ayon_launcher_process",
    "is_running_from_build",
    "is_using_ayon_console",
    "is_headless_mode_enabled",
    "is_staging_enabled",
    "is_dev_mode_enabled",
    "is_in_tests",
    "get_settings_variant",
]
