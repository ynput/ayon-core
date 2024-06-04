import copy
from typing import Any

from .publish_plugins import DEFAULT_PUBLISH_VALUES


def _convert_imageio_configs_0_3_1(overrides):
    """Imageio config settings did change to profiles since 0.3.1. ."""
    imageio_overrides = overrides.get("imageio") or {}
    if (
        "ocio_config" not in imageio_overrides
        or "filepath" not in imageio_overrides["ocio_config"]
    ):
        return

    ocio_config = imageio_overrides.pop("ocio_config")

    filepath = ocio_config["filepath"]
    if not filepath:
        return
    first_filepath = filepath[0]
    ocio_config_profiles = imageio_overrides.setdefault(
        "ocio_config_profiles", []
    )
    base_value = {
        "type": "builtin_path",
        "product_name": "",
        "host_names": [],
        "task_names": [],
        "task_types": [],
        "custom_path": "",
        "builtin_path": "{BUILTIN_OCIO_ROOT}/aces_1.2/config.ocio"
    }
    if first_filepath in (
        "{BUILTIN_OCIO_ROOT}/aces_1.2/config.ocio",
        "{BUILTIN_OCIO_ROOT}/nuke-default/config.ocio",
    ):
        base_value["type"] = "builtin_path"
        base_value["builtin_path"] = first_filepath
    else:
        base_value["type"] = "custom_path"
        base_value["custom_path"] = first_filepath

    ocio_config_profiles.append(base_value)


def _convert_validate_version_0_3_3(publish_overrides):
    """ValidateVersion plugin changed in 0.3.3."""
    if "ValidateVersion" not in publish_overrides:
        return

    validate_version = publish_overrides["ValidateVersion"]
    # Already new settings
    if "plugin_state_profiles" in validate_version:
        return

    # Use new default profile as base
    profile = copy.deepcopy(
        DEFAULT_PUBLISH_VALUES["ValidateVersion"]["plugin_state_profiles"][0]
    )
    # Copy values from old overrides to new overrides
    for key in {
        "enabled",
        "optional",
        "active",
    }:
        if key not in validate_version:
            continue
        profile[key] = validate_version.pop(key)

    validate_version["plugin_state_profiles"] = [profile]


def _conver_publish_plugins(overrides):
    if "publish" not in overrides:
        return
    _convert_validate_version_0_3_3(overrides["publish"])


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_imageio_configs_0_3_1(overrides)
    _conver_publish_plugins(overrides)
    return overrides
