from __future__ import annotations

import functools
import warnings
from typing import Optional, Any

from ayon_core.lib import Logger
from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.settings import get_project_settings

log = Logger.get_logger(__name__)


def _get_versioning_start_wrap(func):
    """Change 'product_type' kwarg to 'product_base_type' compatibility."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if "product_type" in kwargs:
            msg = (
                "Found 'product_type' kwarg in 'get_versioning_start',"
                " use 'product_base_type' instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)

            kwargs["product_base_type"] = kwargs.pop("product_type")

        if len(args) > 6:
            msg = (
                "Got more positional arguments for 'get_versioning_start'"
                " than expected. Please use explicit kwargs instead."
            )
            log.warning(msg)
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            args, rem = args[:6], args[6:]
            kwargs["project_settings"] = rem[0]

        return func(*args, **kwargs)
    return wrapper


@_get_versioning_start_wrap
def get_versioning_start(
    project_name: str,
    host_name: str,
    task_name: Optional[str] = None,
    task_type: Optional[str] = None,
    product_base_type: Optional[str] = None,
    product_name: Optional[str] = None,
    *,
    project_settings: Optional[dict[str, Any]] = None,
) -> int:
    """Get anatomy versioning start"""
    if not project_settings:
        project_settings = get_project_settings(project_name)

    version_start = 1
    settings = project_settings["core"]
    profiles = settings["version_start_category"]["profiles"]

    if not profiles:
        return version_start

    filtering_criteria = {
        "host_names": host_name,
        "product_base_types": product_base_type,
        "product_names": product_name,
        "task_names": task_name,
        "task_types": task_type,
    }
    profile = filter_profiles(profiles, filtering_criteria)

    if profile is None:
        return version_start

    return profile["version_start"]
