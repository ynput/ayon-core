from __future__ import annotations

import warnings
from typing import Optional, Any

from ayon_core.lib import Logger
from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.settings import get_project_settings

log = Logger.get_logger(__name__)


def get_versioning_start(
    project_name: str,
    host_name: str,
    task_name: Optional[str] = None,
    task_type: Optional[str] = None,
    product_type: Optional[str] = None,
    product_name: Optional[str] = None,
    product_base_type: Optional[str] = None,
    *,
    project_settings: Optional[dict[str, Any]] = None,
) -> int:
    """Get anatomy versioning start"""
    if not project_settings:
        project_settings = get_project_settings(project_name)

    if product_base_type is None and product_type:
        msg = (
            "Found 'product_type' kwarg in 'get_versioning_start',"
            " use 'product_base_type' instead."
        )
        log.warning(msg)
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        product_base_type = product_type

    version_start = 1
    settings = project_settings["core"]
    profiles = settings["version_start_category"]["profiles"]

    if not profiles:
        return version_start

    filtering_criteria = {
        "host_names": host_name,
        "product_types": product_base_type,
        "product_names": product_name,
        "task_names": task_name,
        "task_types": task_type,
    }
    profile = filter_profiles(profiles, filtering_criteria)

    if profile is None:
        return version_start

    return profile["version_start"]
