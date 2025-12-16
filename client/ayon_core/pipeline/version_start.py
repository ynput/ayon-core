from __future__ import annotations
from typing import Optional, Any

from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.settings import get_project_settings


def get_versioning_start(
    project_name: str,
    host_name: str,
    task_name: Optional[str] = None,
    task_type: Optional[str] = None,
    product_type: Optional[str] = None,
    product_name: Optional[str] = None,
    project_settings: Optional[dict[str, Any]] = None,
):
    """Get anatomy versioning start"""
    if not project_settings:
        project_settings = get_project_settings(project_name)

    version_start = 1
    settings = project_settings["core"]
    profiles = settings.get("version_start_category", {}).get("profiles", [])

    if not profiles:
        return version_start

    # TODO use 'product_types' and 'product_name' instead of
    #   'families' and 'subsets'
    filtering_criteria = {
        "host_names": host_name,
        "product_types": product_type,
        "product_names": product_name,
        "task_names": task_name,
        "task_types": task_type,
    }
    profile = filter_profiles(profiles, filtering_criteria)

    if profile is None:
        return version_start

    return profile["version_start"]
