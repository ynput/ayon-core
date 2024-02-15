import os
import json
import logging
import copy

from .constants import (
    M_OVERRIDDEN_KEY,

    METADATA_KEYS,

    SYSTEM_SETTINGS_KEY,
    PROJECT_SETTINGS_KEY,
    DEFAULT_PROJECT_KEY
)

from .ayon_settings import (
    get_ayon_project_settings,
    get_ayon_system_settings,
    get_ayon_settings,
)

log = logging.getLogger(__name__)

# Py2 + Py3 json decode exception
JSON_EXC = getattr(json.decoder, "JSONDecodeError", ValueError)


# Path to default settings
DEFAULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "defaults"
)

# Variable where cache of default settings are stored
_DEFAULT_SETTINGS = None


def clear_metadata_from_settings(values):
    """Remove all metadata keys from loaded settings."""
    if isinstance(values, dict):
        for key in tuple(values.keys()):
            if key in METADATA_KEYS:
                values.pop(key)
            else:
                clear_metadata_from_settings(values[key])
    elif isinstance(values, list):
        for item in values:
            clear_metadata_from_settings(item)


def get_local_settings():
    # TODO implement ayon implementation
    return {}


def load_openpype_default_settings():
    """Load openpype default settings."""
    return load_jsons_from_dir(DEFAULTS_DIR)


def reset_default_settings():
    """Reset cache of default settings. Can't be used now."""
    global _DEFAULT_SETTINGS
    _DEFAULT_SETTINGS = None


def _get_default_settings():
    return load_openpype_default_settings()


def get_default_settings():
    """Get default settings.

    Todo:
        Cache loaded defaults.

    Returns:
        dict: Loaded default settings.
    """
    global _DEFAULT_SETTINGS
    if _DEFAULT_SETTINGS is None:
        _DEFAULT_SETTINGS = _get_default_settings()
    return copy.deepcopy(_DEFAULT_SETTINGS)


def load_json_file(fpath):
    # Load json data
    try:
        with open(fpath, "r") as opened_file:
            return json.load(opened_file)

    except JSON_EXC:
        log.warning(
            "File has invalid json format \"{}\"".format(fpath),
            exc_info=True
        )
    return {}


def load_jsons_from_dir(path, *args, **kwargs):
    """Load all .json files with content from entered folder path.

    Data are loaded recursively from a directory and recreate the
    hierarchy as a dictionary.

    Entered path hierarchy:
    |_ folder1
    | |_ data1.json
    |_ folder2
      |_ subfolder1
        |_ data2.json

    Will result in:
    ```javascript
    {
        "folder1": {
            "data1": "CONTENT OF FILE"
        },
        "folder2": {
            "subfolder1": {
                "data2": "CONTENT OF FILE"
            }
        }
    }
    ```

    Args:
        path (str): Path to the root folder where the json hierarchy starts.

    Returns:
        dict: Loaded data.
    """
    output = {}

    path = os.path.normpath(path)
    if not os.path.exists(path):
        # TODO warning
        return output

    sub_keys = list(kwargs.pop("subkeys", args))
    for sub_key in tuple(sub_keys):
        _path = os.path.join(path, sub_key)
        if not os.path.exists(_path):
            break

        path = _path
        sub_keys.pop(0)

    base_len = len(path) + 1
    for base, _directories, filenames in os.walk(path):
        base_items_str = base[base_len:]
        if not base_items_str:
            base_items = []
        else:
            base_items = base_items_str.split(os.path.sep)

        for filename in filenames:
            basename, ext = os.path.splitext(filename)
            if ext == ".json":
                full_path = os.path.join(base, filename)
                value = load_json_file(full_path)
                dict_keys = base_items + [basename]
                output = subkey_merge(output, value, dict_keys)

    for sub_key in sub_keys:
        output = output[sub_key]
    return output


def subkey_merge(_dict, value, keys):
    key = keys.pop(0)
    if not keys:
        _dict[key] = value
        return _dict

    if key not in _dict:
        _dict[key] = {}
    _dict[key] = subkey_merge(_dict[key], value, keys)

    return _dict


def merge_overrides(source_dict, override_dict):
    """Merge data from override_dict to source_dict."""

    if M_OVERRIDDEN_KEY in override_dict:
        overridden_keys = set(override_dict.pop(M_OVERRIDDEN_KEY))
    else:
        overridden_keys = set()

    for key, value in override_dict.items():
        if (key in overridden_keys or key not in source_dict):
            source_dict[key] = value

        elif isinstance(value, dict) and isinstance(source_dict[key], dict):
            source_dict[key] = merge_overrides(source_dict[key], value)

        else:
            source_dict[key] = value
    return source_dict


def get_site_local_overrides(project_name, site_name, local_settings=None):
    """Site overrides from local settings for passet project and site name.

    Args:
        project_name (str): For which project are overrides.
        site_name (str): For which site are overrides needed.
        local_settings (dict): Preloaded local settings. They are loaded
            automatically if not passed.
    """
    # Check if local settings were passed
    if local_settings is None:
        local_settings = get_local_settings()

    output = {}

    # Skip if local settings are empty
    if not local_settings:
        return output

    local_project_settings = local_settings.get("projects") or {}

    # Prepare overrides for entered project and for default project
    project_locals = None
    if project_name:
        project_locals = local_project_settings.get(project_name)
    default_project_locals = local_project_settings.get(DEFAULT_PROJECT_KEY)

    # First load and use local settings from default project
    if default_project_locals and site_name in default_project_locals:
        output.update(default_project_locals[site_name])

    # Apply project specific local settings if there are any
    if project_locals and site_name in project_locals:
        output.update(project_locals[site_name])

    return output


def get_current_project_settings():
    """Project settings for current context project.

    Project name should be stored in environment variable `AYON_PROJECT_NAME`.
    This function should be used only in host context where environment
    variable must be set and should not happen that any part of process will
    change the value of the enviornment variable.
    """
    project_name = os.environ.get("AYON_PROJECT_NAME")
    if not project_name:
        raise ValueError(
            "Missing context project in environemt variable `AYON_PROJECT_NAME`."
        )
    return get_project_settings(project_name)


def get_general_environments():
    settings = get_ayon_settings()
    return json.loads(settings["core"]["environments"])


def get_system_settings(*args, **kwargs):
    default_settings = get_default_settings()[SYSTEM_SETTINGS_KEY]
    return get_ayon_system_settings(default_settings)


def get_project_settings(project_name, *args, **kwargs):
    default_settings = get_default_settings()[PROJECT_SETTINGS_KEY]
    return get_ayon_project_settings(default_settings, project_name)
