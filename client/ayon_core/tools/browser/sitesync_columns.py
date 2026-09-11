"""Site Sync columns implemented through the Browser extension contract."""
# TODO: This should move to Site Sync addon

from __future__ import annotations

from typing import Any

from ayon_core.addon import AddonsManager
from ayon_core.lib import NestedCacheItem
from ayon_core.ui.components.table_model import FilterEntry, TableColumn

from .columns import (
    BrowserColumnContext,
    BrowserColumnProvider,
    BrowserColumnServices,
)

ACTIVE_COLUMN_KEY = "sitesync:active"
REMOTE_COLUMN_KEY = "sitesync:remote"
ACTIVE_FILTER_KEY = "sitesync:activeStatus"
REMOTE_FILTER_KEY = "sitesync:remoteStatus"

AVAILABLE = "Available"
PARTIAL = "Partial"
UNAVAILABLE = "Unavailable"
STATUS_VALUES = [AVAILABLE, PARTIAL, UNAVAILABLE]


def _default_version_availability():
    return 0, 0


class SiteSyncBrowserColumnProvider(BrowserColumnProvider):
    """Provide deferred Site Sync availability columns."""

    identifier = "sitesync"
    column_keys = frozenset({
        ACTIVE_COLUMN_KEY,
        REMOTE_COLUMN_KEY,
    })
    filter_keys = frozenset({
        ACTIVE_FILTER_KEY,
        REMOTE_FILTER_KEY,
    })

    lifetime = 60  # In seconds (minute by default)
    status_lifetime = 20

    def __init__(self, services: BrowserColumnServices) -> None:
        self._services = services

        self._site_icons = None
        self._sitesync_enabled_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._active_site_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._remote_site_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._version_availability_cache = NestedCacheItem(
            levels=2,
            default_factory=_default_version_availability,
            lifetime=self.status_lifetime
        )
        addons_manager = AddonsManager()
        self._sitesync_addon = addons_manager.get("sitesync")

    def get_columns(
        self,
        context: BrowserColumnContext,
    ) -> list[TableColumn]:
        if not self._is_enabled(context):
            return []
        return [
            TableColumn(
                ACTIVE_COLUMN_KEY,
                "Active Site",
                width=100,
                sortable=False,
                icon="download",
                entity="Site Sync",
            ),
            TableColumn(
                REMOTE_COLUMN_KEY,
                "Remote Site",
                width=100,
                sortable=False,
                icon="upload",
                entity="Site Sync",
            ),
        ]

    def get_filters(
        self,
        context: BrowserColumnContext,
    ) -> list[FilterEntry]:
        if not self._is_enabled(context):
            return []
        return [
            FilterEntry(
                ACTIVE_FILTER_KEY,
                "Active Site",
                values=list(STATUS_VALUES),
                icon="download",
                entity="Site Sync",
            ),
            FilterEntry(
                REMOTE_FILTER_KEY,
                "Remote Site",
                values=list(STATUS_VALUES),
                icon="upload",
                entity="Site Sync",
            ),
        ]

    def enrich_rows(
        self,
        context: BrowserColumnContext,
        rows: list[dict],
    ) -> None:
        project_name = context.project_name
        if (
            not project_name
            or not self._is_sitesync_enabled(project_name)
        ):
            return

        rows_by_version_id: dict[str, list[dict]] = {}
        for row in rows:
            if row.get("entityType") == "Folder":
                continue
            version_id = row.get("_version_id") or row.get("id")
            if not version_id or str(version_id).startswith("grp:"):
                continue
            rows_by_version_id.setdefault(str(version_id), []).append(row)

        if not rows_by_version_id:
            return

        version_ids = set(rows_by_version_id)
        availability = self._get_version_sync_availability(
            project_name, version_ids
        )
        representation_counts = (
            self._services.get_versions_representation_count(
                project_name,
                version_ids,
            )
        )

        active_site_name = self._get_active_site_name(project_name)
        remote_site_name = self._get_remote_site_name(project_name)
        active_icon_def = self._get_active_site_icon_def(project_name)
        remote_icon_def = self._get_remote_site_icon_def(project_name)

        for version_id, version_rows in rows_by_version_id.items():
            active, remote = availability.get(version_id, (0, 0))
            total = representation_counts.get(version_id, 0)
            active_status = self._status(active, total)
            remote_status = self._status(remote, total)
            values = {
                ACTIVE_COLUMN_KEY: self._display(active, total),
                REMOTE_COLUMN_KEY: self._display(remote, total),
                ACTIVE_FILTER_KEY: active_status,
                REMOTE_FILTER_KEY: remote_status,
            }
            if active_icon_def:
                values[f"{ACTIVE_COLUMN_KEY}__icon"] = active_icon_def
            if active_site_name:
                values[f"{ACTIVE_COLUMN_KEY}__tooltip"] = active_site_name
            if remote_icon_def:
                values[f"{REMOTE_COLUMN_KEY}__icon"] = remote_icon_def
            if remote_site_name:
                values[f"{REMOTE_COLUMN_KEY}__tooltip"] = remote_site_name
            for row in version_rows:
                row.update(values)

    @staticmethod
    def _display(available: int, total: int) -> str:
        return f"{available}/{total}"

    @staticmethod
    def _status(available: int, total: int) -> str:
        if available <= 0 or total <= 0:
            return UNAVAILABLE
        if available >= total:
            return AVAILABLE
        return PARTIAL

    def _is_enabled(self, context: BrowserColumnContext) -> bool:
        return self._is_sitesync_enabled(
            context.project_name
        )

    def _is_sitesync_enabled(self, project_name: str | None = None) -> bool:
        """Site sync is enabled for a project.

        Returns false if site sync addon is not available or enabled
            or project has disabled it.

        Args:
            project_name (Union[str, None]): Project name. If project name
                is 'None', True is returned if site sync addon
                is available and enabled.

        Returns:
            bool: Site sync is enabled.
        """

        if not self._is_sitesync_addon_enabled():
            return False
        cache = self._sitesync_enabled_cache[project_name]
        if not cache.is_valid:
            enabled = True
            if project_name:
                enabled = self._sitesync_addon.is_project_enabled(
                    project_name, single=True
                )
            cache.update_data(enabled)
        return cache.get_data()

    def _get_active_site_name(self, project_name: str) -> str | None:
        """Active site name for a project.

        Args:
            project_name (str): Project name.

        Returns:
            str | None: Remote site name.
        """

        cache = self._active_site_cache[project_name]
        if not cache.is_valid:
            site_name = None
            if project_name and self._is_sitesync_addon_enabled():
                site_name = self._sitesync_addon.get_active_site(project_name)
            cache.update_data(site_name)
        return cache.get_data()

    def _get_remote_site_name(self, project_name: str):
        """Remote site name for a project.

        Args:
            project_name (str): Project name.

        Returns:
            str | None: Remote site name.

        """
        cache = self._remote_site_cache[project_name]
        if not cache.is_valid:
            site_name = None
            if project_name and self._is_sitesync_addon_enabled():
                site_name = self._sitesync_addon.get_remote_site(project_name)
            cache.update_data(site_name)
        return cache.get_data()

    def _get_site_icon_def(self, project_name, site_name):
        # use different icon for studio even if provider is 'local_drive'
        if site_name == self._sitesync_addon.DEFAULT_SITE:
            provider = "studio"
        else:
            provider = self._get_provider_for_site(project_name, site_name)
        return self._get_provider_icon(provider)

    def _get_active_site_icon_def(
        self, project_name: str
    ) -> dict[str, Any] | None:
        """Active site icon definition.

        Args:
            project_name (Union[str, None]): Name of project.

        Returns:
            Union[dict[str, Any], None]: Site icon definition.
        """
        active_site = self._get_active_site_name(project_name)
        return self._get_site_icon_def(project_name, active_site)

    def _get_remote_site_icon_def(
        self, project_name: str
    ) -> dict[str, Any] | None:
        """Remote site icon definition.

        Args:
            project_name (str): Name of project.

        Returns:
            Union[dict[str, Any], None]: Site icon definition.

        """
        remote_site = self._get_remote_site_name(project_name)
        return self._get_site_icon_def(project_name, remote_site)

    def _get_version_sync_availability(self, project_name, version_ids):
        """Returns how many representations are available on sites.

        Returned value `{version_id: (4, 6)}` denotes that locally are
            available 4 and remotely 6 representation.
        NOTE: Available means they were synced to site.

        Returns:
            dict[str, tuple[int, int]]

        """
        output = {}
        project_cache = self._version_availability_cache[project_name]
        invalid_ids = set()
        for version_id in version_ids:
            repre_cache = project_cache[version_id]
            if repre_cache.is_valid:
                output[version_id] = repre_cache.get_data()
            else:
                invalid_ids.add(version_id)

        if invalid_ids:
            self._refresh_version_availability(
                project_name, invalid_ids
            )
            for version_id in invalid_ids:
                version_cache = project_cache[version_id]
                output[version_id] = version_cache.get_data()
        return output

    def _is_sitesync_addon_enabled(self):
        """
        Returns:
            bool: Site sync addon is enabled.
        """

        if self._sitesync_addon is None:
            return False
        return self._sitesync_addon.enabled

    def _get_provider_for_site(self, project_name, site_name):
        """Provider for a site.

        Args:
            project_name (str): Project name.
            site_name (str): Site name.

        Returns:
            Union[str, None]: Provider name.
        """

        if not self._is_sitesync_addon_enabled():
            return None
        return self._sitesync_addon.get_provider_for_site(
            project_name, site_name
        )

    def _get_provider_icon(self, provider):
        """site provider icons.

        Returns:
            Union[dict[str, Any], None]: Icon of site provider.
        """

        if not provider:
            return None

        if self._site_icons is None:
            self._site_icons = self._sitesync_addon.get_site_icons()
        return self._site_icons.get(provider)

    def _refresh_version_availability(self, project_name, version_ids):
        if not project_name or not version_ids:
            return
        project_cache = self._version_availability_cache[project_name]

        avail_by_id = self._sitesync_addon.get_version_availability(
            project_name,
            version_ids,
            self._get_active_site_name(project_name),
            self._get_remote_site_name(project_name),
        )
        for version_id in version_ids:
            status = avail_by_id.get(version_id)
            if status is None:
                status = _default_version_availability()
            project_cache[version_id].update_data(status)
