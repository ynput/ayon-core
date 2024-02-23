"""Helper functionality to convert AYON settings to OpenPype v3 settings.

The settings are converted, so we can use v3 code with AYON settings. Once
the code of and addon is converted to full AYON addon which expect AYON
settings the conversion function can be removed.

The conversion is hardcoded -> there is no other way how to achieve the result.

Main entrypoints are functions:
- convert_project_settings - convert settings to project settings
- convert_system_settings - convert settings to system settings
# Both getters cache values
- get_ayon_project_settings - replacement for 'get_project_settings'
- get_ayon_system_settings - replacement for 'get_system_settings'
"""
import os
import collections
import json
import copy
import time

import six

from ayon_core.client import get_ayon_server_api_connection


def _convert_color(color_value):
    if isinstance(color_value, six.string_types):
        color_value = color_value.lstrip("#")
        color_value_len = len(color_value)
        _color_value = []
        for idx in range(color_value_len // 2):
            _color_value.append(int(color_value[idx:idx + 2], 16))
        for _ in range(4 - len(_color_value)):
            _color_value.append(255)
        return _color_value

    if isinstance(color_value, list):
        # WARNING R,G,B can be 'int' or 'float'
        # - 'float' variant is using 'int' for min: 0 and max: 1
        if len(color_value) == 3:
            # Add alpha
            color_value.append(255)
        else:
            # Convert float alha to int
            alpha = int(color_value[3] * 255)
            if alpha > 255:
                alpha = 255
            elif alpha < 0:
                alpha = 0
            color_value[3] = alpha
    return color_value


def _convert_general(ayon_settings, output, default_settings):
    output["core"] = ayon_settings["core"]
    version_check_interval = (
        default_settings["general"]["version_check_interval"]
    )
    output["general"] = {
        "version_check_interval": version_check_interval
    }


def _convert_modules_system(
    ayon_settings, output, addon_versions, default_settings
):
    for key in {
        "timers_manager",
        "clockify",
        "royalrender",
        "deadline",
    }:
        if addon_versions.get(key):
            output[key] = ayon_settings
        else:
            output.pop(key, None)

    modules_settings = output["modules"]
    for module_name in (
        "sync_server",
        "job_queue",
        "addon_paths",
    ):
        settings = default_settings["modules"][module_name]
        if "enabled" in settings:
            settings["enabled"] = False
        modules_settings[module_name] = settings

    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

        # Make sure addons have access to settings in initialization
        # - AddonsManager passes only modules settings into initialization
        if key not in modules_settings:
            modules_settings[key] = value


def is_dev_mode_enabled():
    """Dev mode is enabled in AYON.

    Returns:
        bool: True if dev mode is enabled.
    """

    return os.getenv("AYON_USE_DEV") == "1"


def convert_system_settings(ayon_settings, default_settings, addon_versions):
    default_settings = copy.deepcopy(default_settings)
    output = {
        "modules": {}
    }
    if "core" in ayon_settings:
        _convert_general(ayon_settings, output, default_settings)

    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

    for key, value in default_settings.items():
        if key not in output:
            output[key] = value

    _convert_modules_system(
        ayon_settings,
        output,
        addon_versions,
        default_settings
    )
    return output


# --------- Project settings ---------
def convert_project_settings(ayon_settings, default_settings):
    default_settings = copy.deepcopy(default_settings)
    output = {}
    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

    for key, value in default_settings.items():
        if key not in output:
            output[key] = value

    return output


class CacheItem:
    lifetime = 10

    def __init__(self, value, outdate_time=None):
        self._value = value
        if outdate_time is None:
            outdate_time = time.time() + self.lifetime
        self._outdate_time = outdate_time

    @classmethod
    def create_outdated(cls):
        return cls({}, 0)

    def get_value(self):
        return copy.deepcopy(self._value)

    def update_value(self, value):
        self._value = value
        self._outdate_time = time.time() + self.lifetime

    @property
    def is_outdated(self):
        return time.time() > self._outdate_time


class _AyonSettingsCache:
    use_bundles = None
    variant = None
    addon_versions = CacheItem.create_outdated()
    studio_settings = CacheItem.create_outdated()
    cache_by_project_name = collections.defaultdict(
        CacheItem.create_outdated)

    @classmethod
    def _use_bundles(cls):
        if _AyonSettingsCache.use_bundles is None:
            con = get_ayon_server_api_connection()
            major, minor, _, _, _ = con.get_server_version_tuple()
            use_bundles = True
            if (major, minor) < (0, 3):
                use_bundles = False
            _AyonSettingsCache.use_bundles = use_bundles
        return _AyonSettingsCache.use_bundles

    @classmethod
    def _get_variant(cls):
        if _AyonSettingsCache.variant is None:
            from ayon_core.lib import is_staging_enabled

            variant = "production"
            if is_dev_mode_enabled():
                variant = cls._get_bundle_name()
            elif is_staging_enabled():
                variant = "staging"

            # Cache variant
            _AyonSettingsCache.variant = variant

            # Set the variant to global ayon api connection
            con = get_ayon_server_api_connection()
            con.set_default_settings_variant(variant)
        return _AyonSettingsCache.variant

    @classmethod
    def _get_bundle_name(cls):
        return os.environ["AYON_BUNDLE_NAME"]

    @classmethod
    def get_value_by_project(cls, project_name):
        cache_item = _AyonSettingsCache.cache_by_project_name[project_name]
        if cache_item.is_outdated:
            con = get_ayon_server_api_connection()
            if cls._use_bundles():
                value = con.get_addons_settings(
                    bundle_name=cls._get_bundle_name(),
                    project_name=project_name,
                    variant=cls._get_variant()
                )
            else:
                value = con.get_addons_settings(project_name)
            cache_item.update_value(value)
        return cache_item.get_value()

    @classmethod
    def _get_addon_versions_from_bundle(cls):
        con = get_ayon_server_api_connection()
        expected_bundle = cls._get_bundle_name()
        bundles = con.get_bundles()["bundles"]
        bundle = next(
            (
                bundle
                for bundle in bundles
                if bundle["name"] == expected_bundle
            ),
            None
        )
        if bundle is not None:
            return bundle["addons"]
        return {}

    @classmethod
    def get_addon_versions(cls):
        cache_item = _AyonSettingsCache.addon_versions
        if cache_item.is_outdated:
            if cls._use_bundles():
                addons = cls._get_addon_versions_from_bundle()
            else:
                con = get_ayon_server_api_connection()
                settings_data = con.get_addons_settings(
                    only_values=False,
                    variant=cls._get_variant()
                )
                addons = settings_data["versions"]
            cache_item.update_value(addons)

        return cache_item.get_value()


def get_ayon_project_settings(default_values, project_name):
    ayon_settings = _AyonSettingsCache.get_value_by_project(project_name)
    return convert_project_settings(ayon_settings, default_values)


def get_ayon_system_settings(default_values):
    addon_versions = _AyonSettingsCache.get_addon_versions()
    ayon_settings = _AyonSettingsCache.get_value_by_project(None)

    return convert_system_settings(
        ayon_settings, default_values, addon_versions
    )


def get_ayon_settings(project_name=None):
    """AYON studio settings.

    Raw AYON settings values.

    Args:
        project_name (Optional[str]): Project name.

    Returns:
        dict[str, Any]: AYON settings.
    """

    return _AyonSettingsCache.get_value_by_project(project_name)
