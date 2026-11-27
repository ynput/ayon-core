from __future__ import annotations

import os
import json
import collections
import copy
import time
import warnings
from typing import Any
from urllib.parse import urlencode

import ayon_api

from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


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


def _get_addons_settings_items(
    studio_bundle_name: str,
    project_bundle_name: str,
    variant: str,
    project_name: str | None = None,
) -> list[dict[str, Any]]:
    """Request settings of all addons.

    Each item contains addon name, version and settings.

    Returns:
        list[dict[str, Any]]: Addon items of the response.

    """
    query_values = {
        key: value
        for key, value in (
            ("bundle_name", studio_bundle_name),
            ("variant", variant),
            ("project_name", project_name),
        )
        if value
    }
    if project_bundle_name != studio_bundle_name:
        query_values["project_bundle_name"] = project_bundle_name

    site_id = ayon_api.get_site_id()
    if site_id:
        query_values["site_id"] = site_id

    response = ayon_api.get(f"settings?{urlencode(query_values)}")
    response.raise_for_status()
    return response.data["addons"]


class _AyonSettingsCache:
    variant = None
    # Addon versions from the last studio settings response
    addon_versions = CacheItem.create_outdated()
    cache_by_project_name = collections.defaultdict(
        CacheItem.create_outdated)

    @classmethod
    def _get_variant(cls):
        if _AyonSettingsCache.variant is None:
            from ayon_core.lib import get_settings_variant

            variant = get_settings_variant()
            # Cache variant
            _AyonSettingsCache.variant = variant

            # Set the variant to global ayon api connection
            ayon_api.set_default_settings_variant(variant)
        return _AyonSettingsCache.variant

    @classmethod
    def _get_studio_bundle_name(cls):
        bundle_name = os.environ.get("AYON_STUDIO_BUNDLE_NAME")
        if bundle_name:
            return bundle_name
        return os.environ["AYON_BUNDLE_NAME"]

    @classmethod
    def _get_project_bundle_name(cls):
        return os.environ["AYON_BUNDLE_NAME"]

    @classmethod
    def _update_cache(cls, project_name: str | None) -> None:
        addon_items = _get_addons_settings_items(
            studio_bundle_name=cls._get_studio_bundle_name(),
            project_bundle_name=cls._get_project_bundle_name(),
            project_name=project_name,
            variant=cls._get_variant(),
        )
        cls.cache_by_project_name[project_name].update_value({
            addon["name"]: addon["settings"]
            for addon in addon_items
        })
        if project_name is None:
            # Studio settings list the addons of the bundle with project
            #   bundle overrides, same as a 'summary' settings request.
            # Updated after settings, so it does not outlive them.
            cls.addon_versions.update_value({
                addon["name"]: addon["version"]
                for addon in addon_items
            })

    @classmethod
    def get_value_by_project(cls, project_name):
        cache_item = _AyonSettingsCache.cache_by_project_name[project_name]
        if cache_item.is_outdated:
            cls._update_cache(project_name)
        return cache_item.get_value()

    @classmethod
    def get_addon_versions(cls) -> dict[str, str]:
        cache_item = _AyonSettingsCache.addon_versions
        if cache_item.is_outdated:
            cls._update_cache(None)
        return cache_item.get_value()


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


def get_studio_addon_versions() -> dict[str, str]:
    """Versions of addons used by the process.

    Addons of the studio bundle with overrides of the project bundle.
    Versions come from the studio settings response, which is cached
    together with studio settings.

    Returns:
        dict[str, str]: Addon versions by addon name, ordered as returned
            by the server.

    """
    return _AyonSettingsCache.get_addon_versions()


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
    """DEPRECATE Project settings for current context project.

    Function requires access to pipeline context which is in
        'ayon_core.pipeline'.

    Returns:
        dict[str, Any]: Project settings for current context project.

    """
    warnings.warn(
        "Used deprecated function 'get_current_project_settings' in"
        " 'ayon_core.settings'. The function was moved to"
        " 'ayon_core.pipeline.context_tools'.",
        DeprecationWarning,
        stacklevel=2
    )
    from ayon_core.pipeline.context_tools import get_current_project_settings

    return get_current_project_settings()
