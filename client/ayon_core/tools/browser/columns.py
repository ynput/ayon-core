"""Extension contract for deferred Browser columns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ayon_core.addon import AddonsManager, IBrowserColumnAddon
from ayon_core.lib import Logger
from ayon_core.ui.components.table_model import FilterEntry, TableColumn

log = Logger.get_logger(__name__)


class BrowserColumnServices:
    """Narrow access to core-owned data useful to column providers."""

    def __init__(self, loader_controller: Any) -> None:
        self._loader_controller = loader_controller

    def get_versions_representation_count(
        self,
        project_name: str,
        version_ids: set[str],
    ) -> dict[str, int]:
        """Return representation counts for a batch of versions."""
        return self._loader_controller.get_versions_representation_count(
            project_name,
            version_ids,
        )

    def get_representation_items(
        self,
        project_name: str,
        version_ids: set[str],
    ) -> list[Any]:
        """Return pre-cached representation items for version IDs."""
        return self._loader_controller.get_representation_items(
            project_name,
            version_ids,
        )


@dataclass(frozen=True)
class BrowserFilter:
    """Active Browser filter passed to a column provider."""

    key: str
    values: tuple[str, ...]
    use_substring: bool = False


@dataclass(frozen=True)
class BrowserColumnContext:
    """Immutable Browser state for column and row providers."""

    project_name: str | None
    category: str
    selected_folder_ids: tuple[str, ...]
    selected_task_ids: tuple[str, ...]
    enabled_column_keys: frozenset[str]
    active_filters: tuple[BrowserFilter, ...]
    group_by_key: str
    include_folder_children: bool

    @property
    def requested_keys(self) -> frozenset[str]:
        """Return keys needed by visible columns or active filters."""
        return self.enabled_column_keys | frozenset(
            item.key for item in self.active_filters
        )

    def filters_for(self, *keys: str) -> tuple[BrowserFilter, ...]:
        """Return active filters matching any of the passed keys."""
        requested = set(keys)
        return tuple(
            item for item in self.active_filters if item.key in requested
        )


class BrowserColumnProvider:
    """Base contract for addon-contributed Browser columns.

    Providers declare every key they own in ``column_keys`` and
    ``filter_keys``. ``enrich_rows`` runs in the Browser's existing
    page-fetch worker. The passed dictionaries already contain all data
    fetched by the core query, so providers should batch any additional
    lookups using the row IDs and must not interact with Qt widgets.
    """

    identifier = ""
    column_keys: frozenset[str] = frozenset()
    filter_keys: frozenset[str] = frozenset()

    def get_columns(
        self,
        context: BrowserColumnContext,
    ) -> list[TableColumn]:
        """Return columns available in the current Browser context."""
        return []

    def get_filters(
        self,
        context: BrowserColumnContext,
    ) -> list[FilterEntry]:
        """Return filters handled by this provider."""
        return []

    def get_required_query_keys(
        self,
        context: BrowserColumnContext,
    ) -> set[str]:
        """Return core column keys that must be included in the base query."""
        return set()

    def enrich_rows(
        self,
        context: BrowserColumnContext,
        rows: list[dict],
    ) -> None:
        """Add provider-owned values to already-fetched row dictionaries."""


class BrowserColumnManager:
    """Discover providers and coordinate deferred row enrichment."""

    def __init__(
        self,
        services: BrowserColumnServices,
        fallback_providers: Iterable[BrowserColumnProvider] = (),
        addon_manager: Any | None = None,
    ) -> None:
        providers = list(
            self._discover_addon_providers(addon_manager, services)
        )
        identifiers = {provider.identifier for provider in providers}
        providers.extend(
            provider
            for provider in fallback_providers
            if provider.identifier not in identifiers
        )
        self._providers = self._validate_providers(providers)

    @staticmethod
    def _discover_addon_providers(
        addon_manager: Any | None,
        services: BrowserColumnServices,
    ) -> list[BrowserColumnProvider]:
        output = []
        manager = addon_manager or AddonsManager()
        for addon in manager.get_enabled_addons():
            if not isinstance(addon, IBrowserColumnAddon):
                continue
            try:
                output.extend(
                    addon.get_browser_column_providers(services)
                )
            except Exception:
                log.exception(
                    "Addon %r failed to provide Browser columns",
                    addon.name,
                )
        return output

    @staticmethod
    def _validate_providers(
        providers: list[BrowserColumnProvider],
    ) -> list[BrowserColumnProvider]:
        output = []
        identifiers = set()
        for provider in providers:
            identifier = str(provider.identifier).strip()
            if not identifier:
                log.warning("Ignoring Browser column provider without an ID")
                continue
            if identifier in identifiers:
                log.warning(
                    "Ignoring duplicate Browser column provider %r",
                    identifier,
                )
                continue
            identifiers.add(identifier)
            output.append(provider)
        return output

    def get_columns(
        self,
        context: BrowserColumnContext,
    ) -> list[TableColumn]:
        """Return contributed columns, rejecting duplicate keys."""
        output = []
        keys = set()
        for provider in self._providers:
            try:
                columns = provider.get_columns(context)
            except Exception:
                log.exception(
                    "Browser column provider %r failed to create columns",
                    provider.identifier,
                )
                continue
            for column in columns:
                if column.key not in provider.column_keys:
                    log.warning(
                        "Ignoring undeclared Browser column key %r from %r",
                        column.key,
                        provider.identifier,
                    )
                    continue
                if column.key in keys:
                    log.warning(
                        "Ignoring duplicate Browser column key %r",
                        column.key,
                    )
                    continue
                keys.add(column.key)
                output.append(column)
        return output

    def get_filters(
        self,
        context: BrowserColumnContext,
    ) -> list[FilterEntry]:
        """Return contributed filters, rejecting duplicate keys."""
        output = []
        keys = set()
        for provider in self._providers:
            try:
                filters = provider.get_filters(context)
            except Exception:
                log.exception(
                    "Browser column provider %r failed to create filters",
                    provider.identifier,
                )
                continue
            for item in filters:
                if item.key not in provider.filter_keys:
                    log.warning(
                        "Ignoring undeclared Browser filter key %r from %r",
                        item.key,
                        provider.identifier,
                    )
                    continue
                if item.key in keys:
                    log.warning(
                        "Ignoring duplicate Browser filter key %r",
                        item.key,
                    )
                    continue
                keys.add(item.key)
                output.append(item)
        return output

    def get_filter_keys(self, context: BrowserColumnContext) -> set[str]:
        """Return filter keys owned by contributed providers."""
        return {
            key
            for provider in self._providers
            for key in provider.filter_keys
        }

    def get_required_query_keys(
        self,
        context: BrowserColumnContext,
    ) -> set[str]:
        """Return base-query fields needed by active providers."""
        output = set()
        for provider in self._providers:
            owned_keys = provider.column_keys | provider.filter_keys
            if context.requested_keys.isdisjoint(owned_keys):
                continue
            try:
                output.update(provider.get_required_query_keys(context))
            except Exception:
                log.exception(
                    "Browser column provider %r failed to request fields",
                    provider.identifier,
                )
        return output

    def enrich_rows(
        self,
        context: BrowserColumnContext,
        rows: list[dict],
    ) -> list[dict]:
        """Run only providers needed by visible columns or active filters."""
        output = rows
        requested_keys = context.requested_keys
        if not output or not requested_keys:
            return output

        for provider in self._providers:
            try:
                owned_keys = provider.column_keys | provider.filter_keys
                if requested_keys.isdisjoint(owned_keys):
                    continue
                provider.enrich_rows(context, output)
            except Exception:
                log.exception(
                    "Browser column provider %r failed to process rows",
                    provider.identifier,
                )
        return output
