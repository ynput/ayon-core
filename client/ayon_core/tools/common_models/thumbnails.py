from __future__ import annotations

import collections
import typing

import ayon_api

from ayon_core.lib import NestedCacheItem
from ayon_core.pipeline.thumbnails import (
    get_thumbnail_path,
    get_entity_thumbnail_path,
)

if typing.TYPE_CHECKING:
    from typing import Literal

    ThumbnailEntityType = Literal["folder", "task", "version"]


class ThumbnailsModel:
    entity_cache_lifetime = 240  # In seconds

    def __init__(self) -> None:
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime
        )
        self._tasks_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime
        )
        self._fallback_paths_cache = NestedCacheItem(
            levels=3, lifetime=self.entity_cache_lifetime
        )
        self._versions_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime
        )

    def reset(self) -> None:
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache.reset()
        self._tasks_cache.reset()
        self._fallback_paths_cache.reset()
        self._versions_cache.reset()

    def get_thumbnail_paths(
        self,
        project_name: str | None,
        entity_type: ThumbnailEntityType,
        entity_ids: set[str],
        use_server_fallback: bool = True,
    ) -> dict[str, str | None]:
        """Get paths to thumbnails of entities.

        Args:
            project_name (str | None): Project name.
            entity_type (ThumbnailEntityType): Entity type.
            entity_ids (set[str]): Entity ids.
            use_server_fallback (bool): Let the server resolve thumbnails
                of entities without own thumbnail, like AYON frontend
                does, e.g. thumbnail of a version is used for a task.
                Requires a request for each such entity, so it should
                not be used from the main thread.

        Returns:
            dict[str, str | None]: Thumbnail path by entity id.

        """
        output = {
            entity_id: None
            for entity_id in entity_ids
        }
        if not project_name or not entity_type or not entity_ids:
            return output

        thumbnail_id_by_entity_id = {}
        if entity_type == "folder":
            thumbnail_id_by_entity_id = self.get_folder_thumbnail_ids(
                project_name, entity_ids
            )

        elif entity_type == "task":
            thumbnail_id_by_entity_id = self.get_task_thumbnail_ids(
                project_name, entity_ids
            )

        elif entity_type == "version":
            thumbnail_id_by_entity_id = self.get_version_thumbnail_ids(
                project_name, entity_ids
            )

        if not thumbnail_id_by_entity_id:
            return output

        entity_ids_by_thumbnail_id = collections.defaultdict(set)
        for entity_id, thumbnail_id in thumbnail_id_by_entity_id.items():
            if thumbnail_id:
                entity_ids_by_thumbnail_id[thumbnail_id].add(entity_id)
            elif use_server_fallback:
                output[entity_id] = self._get_fallback_path(
                    project_name, entity_type, entity_id
                )

        for thumbnail_id, entity_ids in entity_ids_by_thumbnail_id.items():
            thumbnail_path = self._get_thumbnail_path(
                project_name, entity_type, next(iter(entity_ids)), thumbnail_id
            )
            if not thumbnail_path:
                continue
            for entity_id in entity_ids:
                output[entity_id] = thumbnail_path

        return output

    def get_folder_thumbnail_ids(
        self, project_name: str, folder_ids: set[str]
    ) -> dict[str, str | None]:
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

    def get_task_thumbnail_ids(
        self, project_name: str, task_ids: set[str]
    ) -> dict[str, str | None]:
        project_cache = self._tasks_cache[project_name]
        output = {}
        missing_cache = set()
        for task_id in task_ids:
            cache = project_cache[task_id]
            if cache.is_valid:
                output[task_id] = cache.get_data()
            else:
                missing_cache.add(task_id)
        self._query_task_thumbnail_ids(project_name, missing_cache)
        for task_id in missing_cache:
            cache = project_cache[task_id]
            output[task_id] = cache.get_data()
        return output

    def get_version_thumbnail_ids(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, str | None]:
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

    def _get_thumbnail_path(
        self,
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_id: str,
        thumbnail_id: str,
    ) -> str | None:
        if not thumbnail_id:
            return None

        project_cache = self._paths_cache[project_name]
        if thumbnail_id in project_cache:
            return project_cache[thumbnail_id]

        filepath = get_thumbnail_path(
            project_name,
            entity_type,
            entity_id,
            thumbnail_id
        )
        project_cache[thumbnail_id] = filepath
        return filepath

    def _get_fallback_path(
        self,
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_id: str,
    ) -> str | None:
        """Thumbnail of an entity that does not have its own thumbnail.

        Server may use thumbnail of a related entity, e.g. of a version
            published to a task. Which thumbnail it is can be found only
            by requesting it.
        """
        cache = (
            self._fallback_paths_cache[project_name][entity_type][entity_id]
        )
        if not cache.is_valid:
            cache.update_data(
                get_entity_thumbnail_path(
                    project_name, entity_type, entity_id
                )
            )
        return cache.get_data()

    def _query_folder_thumbnail_ids(
        self, project_name: str, folder_ids: set[str]
    ) -> None:
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

    def _query_task_thumbnail_ids(
        self, project_name: str, task_ids: set[str]
    ) -> None:
        if not project_name or not task_ids:
            return

        tasks = ayon_api.get_tasks(
            project_name,
            task_ids=task_ids,
            fields=["id", "thumbnailId"]
        )
        project_cache = self._tasks_cache[project_name]
        for task in tasks:
            project_cache[task["id"]] = task["thumbnailId"]

    def _query_version_thumbnail_ids(
        self, project_name: str, version_ids: set[str]
    ) -> None:
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
