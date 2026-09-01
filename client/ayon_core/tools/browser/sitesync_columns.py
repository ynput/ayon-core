"""Site Sync columns implemented through the Browser extension contract."""
# TODO: This should move to Site Sync addon

from __future__ import annotations

from typing import Any

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

    def __init__(
        self,
        sitesync_api: Any,
        services: BrowserColumnServices,
    ) -> None:
        self._sitesync_api = sitesync_api
        self._services = services

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
            or not self._sitesync_api.is_sitesync_enabled(project_name)
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
        availability = (
            self._sitesync_api.get_version_sync_availability(
                project_name,
                version_ids,
            )
        )
        representation_counts = (
            self._services.get_versions_representation_count(
                project_name,
                version_ids,
            )
        )
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
        return self._sitesync_api.is_sitesync_enabled(
            context.project_name
        )
