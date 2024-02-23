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
            from ayon_core.lib import is_staging_enabled, is_dev_mode_enabled

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


def get_ayon_system_settings():
    return _AyonSettingsCache.get_value_by_project(None)


def get_ayon_settings(project_name=None):
    """AYON studio settings.

    Raw AYON settings values.

    Args:
        project_name (Optional[str]): Project name.

    Returns:
        dict[str, Any]: AYON settings.
    """

    return _AyonSettingsCache.get_value_by_project(project_name)
