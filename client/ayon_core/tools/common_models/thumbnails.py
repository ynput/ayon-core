from __future__ import annotations

import collections
import os
import threading
import typing
from typing import Callable

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query

from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.lib.cache import CacheItem
from ayon_core.pipeline.thumbnails import (
    get_thumbnail_path,
    get_entity_thumbnail_path,
    get_project_thumbnail_path,
)

if typing.TYPE_CHECKING:
    from typing import Literal

    ThumbnailEntityType = Literal["folder", "task", "version", "project"]


class ThumbnailsModel:
    """Paths to thumbnails of entities.

    The model can be used from multiple threads at the same time.
    """
    entity_cache_lifetime = 240  # In seconds
    log = Logger.get_logger("ThumbnailsModel")

    def __init__(self) -> None:
        # Guards the caches, is not held when server is requested. Cache
        #   items received before a request are filled after the request,
        #   if the model was reset in the meantime the items are not part
        #   of the caches anymore and the outdated result is not cached.
        self._lock = threading.Lock()
        # All projects are queried at once, more threads asking at the same
        #   time should wait for the result of a single query
        self._projects_query_lock = threading.Lock()
        # Paths are cached only for a while. A failed download is tried
        #   again and a file removed from disk is downloaded again.
        self._paths_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime
        )
        self._thumbnail_ids_cache = NestedCacheItem(
            levels=3, lifetime=self.entity_cache_lifetime
        )
        self._fallback_paths_cache = NestedCacheItem(
            levels=3, lifetime=self.entity_cache_lifetime
        )
        # 'updatedAt' of projects, changes with thumbnail of a project
        self._projects_updated_at_cache = CacheItem(
            default_factory=dict, lifetime=self.entity_cache_lifetime
        )

    def reset(self) -> None:
        with self._lock:
            self._paths_cache.reset()
            self._thumbnail_ids_cache.reset()
            self._fallback_paths_cache.reset()
            # New object, a running query must not fill the new cache
            self._projects_updated_at_cache = CacheItem(
                default_factory=dict, lifetime=self.entity_cache_lifetime
            )

    def get_thumbnail_paths(
        self,
        project_name: str | None,
        entity_type: ThumbnailEntityType,
        entity_ids: set[str],
        use_server_fallback: bool = True,
    ) -> dict[str, str | None]:
        """Get paths to thumbnails of entities.

        Thumbnails of projects are received using entity type 'project',
        in that case entity ids are project names and 'project_name' is
        ignored.

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
        if entity_type == "project":
            return self._get_project_thumbnail_paths(output)

        if (
            not project_name
            or not entity_ids
            or entity_type not in ("folder", "task", "version")
        ):
            return output

        thumbnail_id_by_entity_id = self._get_thumbnail_ids(
            project_name, entity_type, entity_ids
        )
        entity_ids_by_thumbnail_id = collections.defaultdict(list)
        for entity_id, thumbnail_id in thumbnail_id_by_entity_id.items():
            if thumbnail_id:
                entity_ids_by_thumbnail_id[thumbnail_id].append(entity_id)
            elif use_server_fallback:
                output[entity_id] = self._get_fallback_path(
                    project_name, entity_type, entity_id
                )

        for thumbnail_id, same_ids in entity_ids_by_thumbnail_id.items():
            thumbnail_path = self._get_thumbnail_path(
                project_name, entity_type, same_ids[0], thumbnail_id
            )
            for entity_id in same_ids:
                output[entity_id] = thumbnail_path

        return output

    def _get_project_thumbnail_paths(
        self, output: dict[str, str | None]
    ) -> dict[str, str | None]:
        updated_at_by_name = self._get_projects_updated_at()
        for project_name in output:
            updated_at = updated_at_by_name.get(project_name)
            if not updated_at:
                continue
            with self._lock:
                item = self._paths_cache[project_name][updated_at]
            output[project_name] = self._get_cached_path(
                item,
                self._receive_project_thumbnail_path,
                project_name,
                "project",
                project_name,
                updated_at,
            )
        return output

    def _receive_project_thumbnail_path(
        self,
        project_name: str,
        _entity_type: ThumbnailEntityType,
        _entity_id: str,
        updated_at: str,
    ) -> str | None:
        return get_project_thumbnail_path(project_name, updated_at)

    def _get_projects_updated_at(self) -> dict[str, str]:
        with self._projects_query_lock:
            with self._lock:
                item = self._projects_updated_at_cache
                if item.is_valid:
                    return item.get_data()

            updated_at_by_name = {}
            try:
                updated_at_by_name = self._query_projects_updated_at()
            except Exception as exc:
                self.log.warning(
                    "Failed to receive projects for thumbnails: %s", exc
                )
            with self._lock:
                item.update_data(updated_at_by_name)
            return updated_at_by_name

    def _query_projects_updated_at(self) -> dict[str, str]:
        con = ayon_api.get_server_api_connection()
        query = projects_graphql_query({"name", "updatedAt"})
        return {
            project["name"]: project["updatedAt"]
            for parsed_data in query.continuous_query(con)
            for project in parsed_data["projects"]
        }

    def get_folder_thumbnail_ids(
        self, project_name: str, folder_ids: set[str]
    ) -> dict[str, str | None]:
        return self._get_thumbnail_ids(project_name, "folder", folder_ids)

    def get_version_thumbnail_ids(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, str | None]:
        return self._get_thumbnail_ids(project_name, "version", version_ids)

    def _get_thumbnail_ids(
        self,
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_ids: set[str],
    ) -> dict[str, str | None]:
        output = {}
        missing_ids = set()
        with self._lock:
            cache = self._thumbnail_ids_cache[project_name][entity_type]
            for entity_id in entity_ids:
                item = cache[entity_id]
                if item.is_valid:
                    output[entity_id] = item.get_data()
                else:
                    missing_ids.add(entity_id)

        if not missing_ids:
            return output

        queried_ids = self._query_thumbnail_ids(
            project_name, entity_type, missing_ids
        )
        with self._lock:
            for entity_id in missing_ids:
                # Entities that were not found are cached too
                thumbnail_id = queried_ids.get(entity_id)
                cache[entity_id] = thumbnail_id
                output[entity_id] = thumbnail_id
        return output

    def _query_thumbnail_ids(
        self,
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_ids: set[str],
    ) -> dict[str, str | None]:
        fields = ["id", "thumbnailId"]
        if entity_type == "folder":
            entities = ayon_api.get_folders(
                project_name, folder_ids=entity_ids, fields=fields
            )
        elif entity_type == "task":
            entities = ayon_api.get_tasks(
                project_name, task_ids=entity_ids, fields=fields
            )
        else:
            entities = ayon_api.get_versions(
                project_name, version_ids=entity_ids, fields=fields
            )
        return {
            entity["id"]: entity["thumbnailId"]
            for entity in entities
        }

    def _get_thumbnail_path(
        self,
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_id: str,
        thumbnail_id: str,
    ) -> str | None:
        with self._lock:
            item = self._paths_cache[project_name][thumbnail_id]
        return self._get_cached_path(
            item,
            get_thumbnail_path,
            project_name,
            entity_type,
            entity_id,
            thumbnail_id,
        )

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
        with self._lock:
            cache = self._fallback_paths_cache[project_name][entity_type]
            item = cache[entity_id]
        return self._get_cached_path(
            item,
            get_entity_thumbnail_path,
            project_name,
            entity_type,
            entity_id,
        )

    def _get_cached_path(
        self,
        item: CacheItem,
        func: Callable[..., str | None],
        project_name: str,
        entity_type: ThumbnailEntityType,
        entity_id: str,
        *args,
    ) -> str | None:
        """Get thumbnail path from cache item, or receive and cache it.

        Thumbnails that failed to be received are cached too, so they are
            not requested again and again. A fail does not affect other
            thumbnails.
        """
        with self._lock:
            is_valid = item.is_valid
            filepath = item.get_data()
        # The file could be removed from disk, e.g. by cleanup of
        #   thumbnails cache in other process
        if is_valid and (filepath is None or os.path.exists(filepath)):
            return filepath

        filepath = None
        try:
            filepath = func(project_name, entity_type, entity_id, *args)
        except Exception as exc:
            self.log.warning(
                "Failed to receive thumbnail of %s '%s' in project '%s': %s",
                entity_type, entity_id, project_name, exc,
            )
        with self._lock:
            item.update_data(filepath)
        return filepath
