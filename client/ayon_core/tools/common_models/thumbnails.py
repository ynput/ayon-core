import collections

import ayon_api

from ayon_core.lib import NestedCacheItem
from ayon_core.pipeline.thumbnails import get_thumbnail_path


class ThumbnailsModel:
    entity_cache_lifetime = 240  # In seconds

    def __init__(self):
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime)
        self._versions_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime)

    def reset(self):
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache.reset()
        self._versions_cache.reset()

    def get_thumbnail_path(self, project_name, thumbnail_id):
        return self._get_thumbnail_path(project_name, thumbnail_id)

    def get_folder_thumbnail_ids(self, project_name, folder_ids):
        project_cache = self._folders_cache[project_name]
        output = {}
        missing_cache = set()
        for folder_id in folder_ids:
            cache = project_cache[folder_id]
            if cache.is_valid:
                output[folder_id] = cache.get_data()
            else:
                missing_cache.add(folder_id)
        self._query_folder_thumbnail_ids(project_name, missing_cache)
        for folder_id in missing_cache:
            cache = project_cache[folder_id]
            output[folder_id] = cache.get_data()
        return output

    def get_version_thumbnail_ids(self, project_name, version_ids):
        project_cache = self._versions_cache[project_name]
        output = {}
        missing_cache = set()
        for version_id in version_ids:
            cache = project_cache[version_id]
            if cache.is_valid:
                output[version_id] = cache.get_data()
            else:
                missing_cache.add(version_id)
        self._query_version_thumbnail_ids(project_name, missing_cache)
        for version_id in missing_cache:
            cache = project_cache[version_id]
            output[version_id] = cache.get_data()
        return output

    def _get_thumbnail_path(self, project_name, thumbnail_id):
        if not thumbnail_id:
            return None

        project_cache = self._paths_cache[project_name]
        if thumbnail_id in project_cache:
            return project_cache[thumbnail_id]

        filepath = get_thumbnail_path(project_name, thumbnail_id)
        project_cache[thumbnail_id] = filepath
        return filepath

    def _query_folder_thumbnail_ids(self, project_name, folder_ids):
        if not project_name or not folder_ids:
            return

        folders = ayon_api.get_folders(
            project_name,
            folder_ids=folder_ids,
            fields=["id", "thumbnailId"]
        )
        project_cache = self._folders_cache[project_name]
        for folder in folders:
            project_cache[folder["id"]] = folder["thumbnailId"]

    def _query_version_thumbnail_ids(self, project_name, version_ids):
        if not project_name or not version_ids:
            return

        versions = ayon_api.get_versions(
            project_name,
            version_ids=version_ids,
            fields=["id", "thumbnailId"]
        )
        project_cache = self._versions_cache[project_name]
        for version in versions:
            project_cache[version["id"]] = version["thumbnailId"]
