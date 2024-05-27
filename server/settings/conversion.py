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


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_imageio_configs_0_3_1(overrides)
    return overrides
