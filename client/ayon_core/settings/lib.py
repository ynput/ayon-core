import os
import json
import logging
import collections
import copy
import time

import ayon_api

log = logging.getLogger(__name__)


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
            major, minor, _, _, _ = ayon_api.get_server_version_tuple()
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
            ayon_api.set_default_settings_variant(variant)
        return _AyonSettingsCache.variant

    @classmethod
    def _get_bundle_name(cls):
        return os.environ["AYON_BUNDLE_NAME"]

    @classmethod
    def get_value_by_project(cls, project_name):
        cache_item = _AyonSettingsCache.cache_by_project_name[project_name]
        if cache_item.is_outdated:
            if cls._use_bundles():
                value = ayon_api.get_addons_settings(
                    bundle_name=cls._get_bundle_name(),
                    project_name=project_name,
                    variant=cls._get_variant()
                )
            else:
                value = ayon_api.get_addons_settings(project_name)
            cache_item.update_value(value)
        return cache_item.get_value()

    @classmethod
    def _get_addon_versions_from_bundle(cls):
        expected_bundle = cls._get_bundle_name()
        bundles = ayon_api.get_bundles()["bundles"]
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
                settings_data = ayon_api.get_addons_settings(
                    only_values=False,
                    variant=cls._get_variant()
                )
                addons = settings_data["versions"]
            cache_item.update_value(addons)

        return cache_item.get_value()


def get_site_local_overrides(project_name, site_name, local_settings=None):
    """Site overrides from local settings for passet project and site name.

    Deprecated:
        This function is not implemented for AYON and will be removed.

    Args:
        project_name (str): For which project are overrides.
        site_name (str): For which site are overrides needed.
        local_settings (dict): Preloaded local settings. They are loaded
            automatically if not passed.
    """

    return {}


def get_ayon_settings(project_name=None):
    """AYON studio settings.

    Raw AYON settings values.

    Args:
        project_name (Optional[str]): Project name.

    Returns:
        dict[str, Any]: AYON settings.
    """

    return _AyonSettingsCache.get_value_by_project(project_name)


def get_studio_settings(*args, **kwargs):
    return _AyonSettingsCache.get_value_by_project(None)


def get_project_settings(project_name, *args, **kwargs):
    return _AyonSettingsCache.get_value_by_project(project_name)


def get_general_environments(studio_settings=None):
    """General studio environment variables.

    Args:
        studio_settings (Optional[dict]): Pre-queried studio settings.

    Returns:
        dict[str, Any]: General studio environment variables.

    """
    if studio_settings is None:
        studio_settings = get_ayon_settings()
    return json.loads(studio_settings["core"]["environments"])


def get_project_environments(project_name, project_settings=None):
    """Project environment variables.

    Args:
        project_name (str): Project name.
        project_settings (Optional[dict]): Pre-queried project settings.

    Returns:
        dict[str, Any]: Project environment variables.

    """
    if project_settings is None:
        project_settings = get_project_settings(project_name)
    return json.loads(
        project_settings["core"]["project_environments"]
    )


def get_current_project_settings():
    """Project settings for current context project.

    Project name should be stored in environment variable `AYON_PROJECT_NAME`.
    This function should be used only in host context where environment
    variable must be set and should not happen that any part of process will
    change the value of the environment variable.
    """
    project_name = os.environ.get("AYON_PROJECT_NAME")
    if not project_name:
        raise ValueError(
            "Missing context project in environemt variable `AYON_PROJECT_NAME`."
        )
    return get_project_settings(project_name)
