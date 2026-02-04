import re
import copy
from typing import Any

from .publish_plugins import DEFAULT_PUBLISH_VALUES

PRODUCT_NAME_REPL_REGEX = re.compile(r"[^<>{}\[\]a-zA-Z0-9_.]")


def _convert_product_base_types_1_8_0(overrides):
    # Staging dir, standard/hero publish templase
    all_profiles = []
    publish_settings = overrides.get("tools", {}).get("publish", {})
    for profile_name in (
        "custom_staging_dir_profiles",
        "template_name_profiles",
        "hero_template_name_profiles",
    ):
        profiles = publish_settings.get(profile_name)
        if profiles:
            all_profiles.append(profiles)

    # Version start
    version_start_s = (
        overrides
        .get("version_start_category", {})
        .get("profiles")
    )
    if version_start_s:
        all_profiles.append(version_start_s)

    # Publish plugins
    publish_plugins = overrides.get("publish", {})
    for settings_parts in (
        ("CollectUSDLayerContributions", "profiles"),
    ):
        found = True
        plugin_settings = publish_plugins
        for part in settings_parts:
            if part not in plugin_settings:
                found = False
                break
            plugin_settings = plugin_settings[part]

        if found and plugin_settings:
            all_profiles.append(plugin_settings)

    # Convert data in profiles
    for profile in all_profiles:
        for old, new in (
            ("product_types", "product_base_types"),
            ("hosts", "host_names"),
            ("tasks", "task_names"),
        ):
            if old in profile and new not in profile:
                profile[new] = profile.pop(old)

    collect_exp_res = publish_plugins.get("CollectExplicitResolution") or {}
    if (
        "product_types" in collect_exp_res
        and "product_base_types" not in collect_exp_res
    ):
        collect_exp_res["product_base_types"] = collect_exp_res.pop(
            "product_types"
        )


def _convert_product_name_templates_1_7_0(overrides):
    product_name_profiles = (
        overrides
        .get("tools", {})
        .get("creator", {})
        .get("product_name_profiles")
    )
    if (
        not product_name_profiles
        or not isinstance(product_name_profiles, list)
    ):
        return

    # Already converted
    item = product_name_profiles[0]
    if "product_base_types" in item or "product_types" not in item:
        return

    # Move product base types to product types
    for item in product_name_profiles:
        item["product_base_types"] = item["product_types"]
        item["product_types"] = []


def _convert_product_name_templates_1_6_5(overrides):
    product_name_profiles = (
        overrides
        .get("tools", {})
        .get("creator", {})
        .get("product_name_profiles")
    )
    if isinstance(product_name_profiles, list):
        for item in product_name_profiles:
            # Remove unsupported product name characters
            template = item.get("template")
            if isinstance(template, str):
                item["template"] = PRODUCT_NAME_REPL_REGEX.sub("", template)

            for new_key, old_key in (
                ("host_names", "hosts"),
                ("task_names", "tasks"),
            ):
                if old_key in item:
                    item[new_key] = item.get(old_key)


def _convert_imageio_configs_0_4_5(overrides):
    """Imageio config settings did change to profiles since 0.4.5."""
    imageio_overrides = overrides.get("imageio") or {}

    # make sure settings are already converted to profiles
    ocio_config_profiles = imageio_overrides.get("ocio_config_profiles")
    if not ocio_config_profiles:
        return

    for profile in ocio_config_profiles:
        if profile.get("type") != "product_name":
            continue

        profile["type"] = "published_product"
        profile["published_product"] = {
            "product_name": profile.pop("product_name"),
            "fallback": {
                "type": "builtin_path",
                "builtin_path": "{BUILTIN_OCIO_ROOT}/aces_1.2/config.ocio",
            },
        }


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


def _convert_oiio_transcode_0_4_5(publish_overrides):
    """ExtractOIIOTranscode plugin changed in 0.4.5."""
    if "ExtractOIIOTranscode" not in publish_overrides:
        return

    transcode_profiles = publish_overrides["ExtractOIIOTranscode"].get(
        "profiles")
    if not transcode_profiles:
        return

    for profile in transcode_profiles:
        outputs = profile.get("outputs")
        if outputs is None:
            return

        for output in outputs:
            # Already new settings
            if "display_view" in output:
                break

            # Fix 'display' -> 'display_view' in 'transcoding_type'
            transcode_type = output.get("transcoding_type")
            if transcode_type == "display":
                output["transcoding_type"] = "display_view"

            # Convert 'display' and 'view' to new values
            output["display_view"] = {
                "display": output.pop("display", ""),
                "view": output.pop("view", ""),
            }


def _convert_publish_plugins(overrides):
    if "publish" not in overrides:
        return
    _convert_validate_version_0_3_3(overrides["publish"])
    _convert_oiio_transcode_0_4_5(overrides["publish"])


def _convert_extract_thumbnail(overrides):
    """ExtractThumbnail config settings did change to profiles."""
    extract_thumbnail_overrides = (
        overrides.get("publish", {}).get("ExtractThumbnail")
    )
    if extract_thumbnail_overrides is None:
        return

    base_value = {
        "product_types": [],
        "host_names": [],
        "task_types": [],
        "task_names": [],
        "product_names": [],
        "integrate_thumbnail": True,
        "target_size": {"type": "source"},
        "duration_split": 0.5,
        "oiiotool_defaults": {
            "type": "colorspace",
            "colorspace": "color_picking",
        },
        "ffmpeg_args": {"input": ["-apply_trc gamma22"], "output": []},
    }
    for key in (
        "product_names",
        "integrate_thumbnail",
        "target_size",
        "duration_split",
        "oiiotool_defaults",
        "ffmpeg_args",
    ):
        if key in extract_thumbnail_overrides:
            base_value[key] = extract_thumbnail_overrides.pop(key)

    extract_thumbnail_profiles = extract_thumbnail_overrides.setdefault(
        "profiles", []
    )
    extract_thumbnail_profiles.append(base_value)


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_imageio_configs_0_3_1(overrides)
    _convert_imageio_configs_0_4_5(overrides)
    _convert_product_name_templates_1_6_5(overrides)
    _convert_product_name_templates_1_7_0(overrides)
    _convert_publish_plugins(overrides)
    _convert_extract_thumbnail(overrides)
    _convert_product_base_types_1_8_0(overrides)
    return overrides
