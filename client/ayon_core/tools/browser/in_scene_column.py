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

import uuid
from dataclasses import dataclass
from typing import Any

import ayon_api

from ayon_core.host import AbstractHost, ILoadHost
from ayon_core.lib import CacheItem, Logger
from ayon_core.pipeline import get_current_context, registered_host
from ayon_core.ui.components.table_model import FilterEntry, TableColumn

from .columns import (
    BrowserColumnContext,
    BrowserColumnProvider,
)

log = Logger.get_logger(__name__)

IN_SCENE_KEY = "inScene"

_LOADED_COLOR = "#50aa50"
_NOT_LOADED_COLOR = "#5a5a5a"


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
        loaded = self._get_loaded_ids(host)
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
        """Drop the cached loaded-ids set.

        A failed Load action didn't change scene state, so only a clean
        finish invalidates the cache.
        """
        if not event.get("error_info"):
            self._loaded_ids_cache.reset()

    def _is_enabled(self) -> bool:
        return self._get_host() is not None

    def _get_host(self) -> AbstractHost | None:
        if self._host is not None:
            return self._host
        return registered_host()

    def _get_loaded_ids(self, host: AbstractHost) -> _LoadedIds:
        """Return version and product ids represented by containers.

        The product ids cost one extra server round trip (version ->
        product) over just resolving versions, but only ever happens on
        a cache miss, and lets a product-grouped row be answered too.
        """
        if self._loaded_ids_cache.is_valid:
            return self._loaded_ids_cache.get_data()

        project_name = self._get_host_project_name(host)
        if not project_name:
            return _LoadedIds()

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
            try:
                uuid.UUID(repre_id)
            except (ValueError, TypeError, AttributeError):
                continue
            repre_ids.add(repre_id)

        version_ids: set[str] = set()
        if repre_ids:
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

        loaded = _LoadedIds(
            version_ids=frozenset(version_ids),
            product_ids=frozenset(product_ids),
        )
        self._loaded_ids_cache.update_data(loaded)
        return self._loaded_ids_cache.get_data()

    @staticmethod
    def _get_host_project_name(host: AbstractHost) -> str | None:
        """Return the project the scene itself belongs to.

        Deliberately the host's own context, not the project currently
        browsed in Browser - those can differ, and a representation id
        only resolves within the project that issued it.
        """
        if hasattr(host, "get_current_context"):
            context = host.get_current_context()
        else:
            context = get_current_context()
        return context.get("project_name")
