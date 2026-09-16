"""Loaded-in-scene column implemented through the Browser extension contract.

Everything the "In Scene" feature needs - the host lookup, container
querying, representation-to-version resolution and caching - lives here
rather than being spread across the Browser controller. The controller
only knows this provider exists; it does not know what a "container" is
or that "load.finished" is relevant to it - this provider subscribes to
that event itself, the same way any other Browser event listener would.

Only meaningful inside a DCC host: a standalone Browser session has no
scene to check versions against, so the column and filter are both
withheld until a host is registered.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import ayon_api

from ayon_core.host import AbstractHost, ILoadHost
from ayon_core.lib import CacheItem, Logger
from ayon_core.pipeline import registered_host
from ayon_core.ui.components.table_model import FilterEntry, TableColumn

from .columns import (
    BrowserColumnContext,
    BrowserColumnProvider,
)
from .server_capabilities import server_supports_representation_filter

log = Logger.get_logger(__name__)

IN_SCENE_KEY = "inScene"

_LOADED_COLOR = "#50aa50"
_NOT_LOADED_COLOR = "#5a5a5a"


# Minimal GraphQL query to get version id + product id from representation
# in a single query
_VERSIONS_BY_REPRESENTATIONS_QUERY = """
query GetVersionsByRepresentations(
  $projectName: String!,
  $representationFilter: String,
) {
  project(name: $projectName) {
    versions(representationFilter: $representationFilter) {
      edges {
        node {
          id
          productId
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class _LoadedIds:
    """Version and product ids resolved from the scene's containers.

    Product ids let a product-grouped row answer "is any version of this
    product loaded", not just its one featured version.
    """

    version_ids: frozenset[str] = frozenset()
    product_ids: frozenset[str] = frozenset()


class InSceneColumnProvider(BrowserColumnProvider):
    """Flags versions represented by containers in the current scene."""

    identifier = "in_scene"
    column_keys = frozenset({IN_SCENE_KEY})
    filter_keys = frozenset({IN_SCENE_KEY})

    #: How long a resolved `_LoadedIds` stays valid. Kept short (rather
    #: than unset) so a container loaded/removed through some other tool
    #: still shows up without waiting on the "load.finished" event this
    #: provider listens for below.
    lifetime = 15  # seconds

    def __init__(
        self,
        host: AbstractHost | None = None,
        loader_controller: Any | None = None,
    ) -> None:
        # `None` defers to `registered_host()` on every lookup, so a host
        # registered after this provider is constructed is still picked
        # up - the same pattern `SceneInventoryController` uses.
        self._host = host
        self._loaded_ids_cache = CacheItem(
            default_factory=_LoadedIds, lifetime=self.lifetime
        )
        self._last_repre_ids: frozenset[str] | None = None
        self._last_project_name: str | None = None
        # Subscribing directly to Browser's own event bus - rather than
        # the controller pushing an "invalidate everything" call into
        # every provider - keeps this provider the only place that knows
        # a fresh Load means its cached scene state is stale.
        if loader_controller is not None:
            loader_controller.register_event_callback(
                "load.finished", self._on_load_finished
            )

    def get_columns(
        self,
        context: BrowserColumnContext,
    ) -> list[TableColumn]:
        if not self._is_enabled():
            return []
        return [
            TableColumn(
                IN_SCENE_KEY, "In Scene",
                width=80,
                sortable=False,
                icon="how_to_reg",
                entity="Version",
            ),
        ]

    def get_filters(
        self,
        context: BrowserColumnContext,
    ) -> list[FilterEntry]:
        if not self._is_enabled():
            return []
        return [
            FilterEntry(
                IN_SCENE_KEY, "In Scene",
                options=["Yes", "No"],
                icon="how_to_reg", entity="Version", single_select=True,
            ),
        ]

    def enrich_rows(
        self,
        context: BrowserColumnContext,
        rows: list[dict],
    ) -> None:
        # `BrowserColumnManager` already only calls this when the column
        # is visible or the filter is active, so the loaded-ids lookup
        # (a host + server round trip on a cache miss) is skipped
        # whenever nobody is looking at this data.
        host = self._get_host()
        if host is None:
            return
        loaded = self._get_loaded_ids(host, context.project_name)
        supported_entity_types = {"Product", "Version"}
        for row in rows:
            if row.get("entityType") not in supported_entity_types:
                continue
            if "has_children" in row:
                # A group-header row. Only the product axis carries a
                # stable product id to check "any version loaded"
                # against - other axes (status, tags, task type, ...)
                # group rows across many products, so there is no
                # single true answer. Leave the cell blank rather than
                # claim "No".
                product_id = row.get("_product_id")
                if product_id is None:
                    continue
                in_scene = product_id in loaded.product_ids
            else:
                in_scene = row.get("id") in loaded.version_ids

            row[IN_SCENE_KEY] = "Yes" if in_scene else "No"
            row[f"{IN_SCENE_KEY}__color"] = (
                _LOADED_COLOR if in_scene else _NOT_LOADED_COLOR
            )

    def _on_load_finished(self, event: dict) -> None:
        """Mark the cached loaded-ids set as needing a recheck."""
        if not event.get("error_info"):
            self._loaded_ids_cache.set_invalid()

    def _is_enabled(self) -> bool:
        return self._get_host() is not None

    def _get_host(self) -> AbstractHost | None:
        if self._host is not None:
            return self._host
        return registered_host()

    def _get_loaded_ids(
        self,
        host: AbstractHost,
        project_name: str | None,
    ) -> _LoadedIds:
        """Return version and product ids represented by loaded containers.

        Args:
            host: The registered host to query containers from.
            project_name: The project name the browser is viewing. Not
              necessarily the current context's project.
        """
        if not project_name:
            return _LoadedIds()

        if project_name != self._last_project_name:
            # Switching project in the browser invalidates everything, because
            # we have queried the loaded representation ids against the project
            # we are viewing only.
            self._last_project_name = project_name
            self._last_repre_ids = None
            self._loaded_ids_cache.set_invalid()

        if self._loaded_ids_cache.is_valid:
            return self._loaded_ids_cache.get_data()

        try:
            if isinstance(host, ILoadHost):
                containers = host.get_containers()
            else:
                containers = host.ls()
        except Exception:
            log.error("Failed to collect loaded versions.", exc_info=True)
            containers = []

        repre_ids = set()
        for container in containers:
            repre_id = container.get("representation")
            if not repre_id or not self._is_uuid(repre_id):
                continue

            # Skip representations from a project other than the one Browser
            # is viewing
            repre_project = container.get("project_name")
            if repre_project and repre_project != project_name:
                continue

            repre_ids.add(repre_id)

        repre_ids = frozenset(repre_ids)
        if repre_ids == self._last_repre_ids:
            # Same representations as last time, keep previous cache
            self._loaded_ids_cache.update_data(
                self._loaded_ids_cache.get_data()
            )
            return self._loaded_ids_cache.get_data()

        # Query version and product ids from server
        loaded = None
        if repre_ids:
            if server_supports_representation_filter():
                loaded = self._resolve_via_representation_filter(
                    project_name, repre_ids
                )
            else:
                loaded = self._resolve_via_representations_then_versions(
                    project_name, repre_ids
                )
        loaded = loaded or _LoadedIds()
        self._last_repre_ids = repre_ids
        self._loaded_ids_cache.update_data(loaded)
        return self._loaded_ids_cache.get_data()

    @staticmethod
    def _is_uuid(value: Any) -> bool:
        try:
            uuid.UUID(value)
        except (ValueError, TypeError, AttributeError):
            return False
        return True

    @staticmethod
    def _resolve_via_representation_filter(
        project_name: str,
        repre_ids: set[str],
    ) -> _LoadedIds | None:
        """Resolve loaded ids in a single round trip, where supported.

        The versions resolver's ``representationFilter`` argument keeps
        versions that have a matching representation, so this needs no
        separate representation -> version lookup at all. Only exists
        on newer servers (see `server_supports_representation_filter`),
        and ``None`` here means "not attempted" - the caller falls back
        to the older two-step resolution.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            return None
        response = con.query_graphql(
            _VERSIONS_BY_REPRESENTATIONS_QUERY,
            {
                "projectName": project_name,
                "representationFilter": json.dumps({
                    "conditions": [{
                        "key": "id",
                        "value": list(repre_ids),
                        "operator": "in",
                    }],
                }),
            },
        )
        if response.errors:
            log.error(
                "representationFilter versions query failed: %s",
                response.errors,
            )
            return None
        edges = (
            response.data["data"]["project"]["versions"]["edges"]
        )
        return _LoadedIds(
            version_ids=frozenset(edge["node"]["id"] for edge in edges),
            product_ids=frozenset(
                edge["node"]["productId"]
                for edge in edges
                if edge["node"].get("productId")
            ),
        )

    @staticmethod
    def _resolve_via_representations_then_versions(
        project_name: str,
        repre_ids: set[str],
    ) -> _LoadedIds:
        """Resolve loaded ids the old way: representations, then versions.

        Two round trips instead of one, for servers whose versions
        resolver does not accept ``representationFilter``.
        """
        representations = ayon_api.get_representations(
            project_name,
            repre_ids,
            fields=["versionId"],
        )
        version_ids = {
            representation["versionId"]
            for representation in representations
            if representation.get("versionId")
        }

        product_ids: set[str] = set()
        if version_ids:
            versions = ayon_api.get_versions(
                project_name,
                version_ids=version_ids,
                fields=["productId"],
            )
            product_ids = {
                version["productId"]
                for version in versions
                if version.get("productId")
            }

        return _LoadedIds(
            version_ids=frozenset(version_ids),
            product_ids=frozenset(product_ids),
        )
