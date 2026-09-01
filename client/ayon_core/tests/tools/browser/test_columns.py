from __future__ import annotations

from unittest.mock import Mock

from ayon_core.addon import IBrowserColumnAddon
from ayon_core.tools.browser.columns import (
    BrowserColumnContext,
    BrowserColumnManager,
    BrowserColumnProvider,
    BrowserColumnServices,
    BrowserFilter,
)
from ayon_core.tools.browser.sitesync_columns import (
    ACTIVE_COLUMN_KEY,
    ACTIVE_FILTER_KEY,
    AVAILABLE,
    PARTIAL,
    REMOTE_COLUMN_KEY,
    REMOTE_FILTER_KEY,
    SiteSyncBrowserColumnProvider,
)
from ayon_core.ui.components.table_model import FilterEntry, TableColumn


def _context(
    *,
    enabled: set[str] | None = None,
    filters: tuple[BrowserFilter, ...] = (),
) -> BrowserColumnContext:
    return BrowserColumnContext(
        project_name="test",
        category="hierarchy",
        selected_folder_ids=("folder",),
        selected_task_ids=(),
        enabled_column_keys=frozenset(enabled or set()),
        active_filters=filters,
        group_by_key="none",
        include_folder_children=False,
    )


class _TestProvider(BrowserColumnProvider):
    identifier = "test"
    column_keys = frozenset({"test:value"})
    filter_keys = frozenset({"test:status"})

    def __init__(self) -> None:
        self.enrich_calls = 0

    def get_columns(self, context):
        return [TableColumn("test:value", "Test Value")]

    def get_filters(self, context):
        return [
            FilterEntry(
                "test:status",
                "Test Status",
                values=["Keep"],
            )
        ]

    def get_required_query_keys(self, context):
        return {"status"}

    def enrich_rows(self, context, rows):
        self.enrich_calls += 1
        for row in rows:
            row["test:value"] = row["id"]
            row["test:status"] = row.get("status")


class _TestAddon(IBrowserColumnAddon):
    name = "test_addon"

    def __init__(self, provider):
        self._provider = provider
        self.services = None

    def get_browser_column_providers(self, services):
        self.services = services
        return [self._provider]


def test_addon_provider_is_discovered_and_skips_unused_columns():
    provider = _TestProvider()
    services = BrowserColumnServices(Mock())
    addon = _TestAddon(provider)
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = [addon]
    manager = BrowserColumnManager(
        services,
        addon_manager=addon_manager,
    )

    assert [column.key for column in manager.get_columns(_context())] == [
        "test:value"
    ]
    assert addon.services is services

    rows = [{"id": "one"}]
    assert manager.enrich_rows(_context(), rows) == rows
    assert provider.enrich_calls == 0
    assert manager.get_required_query_keys(_context()) == set()

    enabled_context = _context(enabled={"test:value"})
    assert manager.get_required_query_keys(enabled_context) == {"status"}
    manager.enrich_rows(enabled_context, rows)
    assert provider.enrich_calls == 1
    assert rows[0]["test:value"] == "one"


def test_provider_filter_requests_enrichment_when_column_is_hidden():
    provider = _TestProvider()
    services = BrowserColumnServices(Mock())
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = []
    manager = BrowserColumnManager(
        services,
        [provider],
        addon_manager=addon_manager,
    )
    context = _context(filters=(
        BrowserFilter("test:status", ("Keep",)),
    ))
    rows = [
        {"id": "one", "status": "Keep"},
        {"id": "two", "status": "Drop"},
    ]

    assert manager.enrich_rows(context, rows) == rows
    assert provider.enrich_calls == 1
    assert rows[0]["test:status"] == "Keep"
    assert rows[1]["test:status"] == "Drop"


def test_sitesync_provider_batches_version_data_from_preloaded_rows():
    loader_controller = Mock()
    loader_controller.is_sitesync_enabled.return_value = True
    loader_controller.get_version_sync_availability.return_value = {
        "version_a": (2, 1),
        "version_b": (1, 3),
    }
    loader_controller.get_versions_representation_count.return_value = {
        "version_a": 2,
        "version_b": 4,
    }
    services = BrowserColumnServices(loader_controller)
    provider = SiteSyncBrowserColumnProvider(
        loader_controller,
        services,
    )
    rows = [
        {"id": "version_a"},
        {"id": "version_b"},
        {"id": "folder_a", "entityType": "Folder"},
        {"id": "grp:product:product_a"},
    ]

    provider.enrich_rows(
        _context(enabled={ACTIVE_COLUMN_KEY, REMOTE_COLUMN_KEY}),
        rows,
    )

    loader_controller.get_version_sync_availability.assert_called_once_with(
        "test",
        {"version_a", "version_b"},
    )
    loader_controller.get_versions_representation_count.assert_called_once_with(
        "test",
        {"version_a", "version_b"},
    )
    assert rows[0][ACTIVE_COLUMN_KEY] == "2/2"
    assert rows[0][REMOTE_COLUMN_KEY] == "1/2"
    assert rows[0][ACTIVE_FILTER_KEY] == AVAILABLE
    assert rows[1][ACTIVE_FILTER_KEY] == PARTIAL
    assert ACTIVE_COLUMN_KEY not in rows[2]
    assert ACTIVE_COLUMN_KEY not in rows[3]


def test_sitesync_filter_requests_deferred_status_values():
    loader_controller = Mock()
    loader_controller.is_sitesync_enabled.return_value = True
    loader_controller.get_version_sync_availability.return_value = {
        "version_a": (2, 0),
        "version_b": (1, 0),
    }
    loader_controller.get_versions_representation_count.return_value = {
        "version_a": 2,
        "version_b": 4,
    }
    services = BrowserColumnServices(loader_controller)
    provider = SiteSyncBrowserColumnProvider(
        loader_controller,
        services,
    )
    manager = BrowserColumnManager(
        services,
        [provider],
        addon_manager=Mock(get_enabled_addons=lambda: []),
    )
    rows = [{"id": "version_a"}, {"id": "version_b"}]
    context = _context(filters=(
        BrowserFilter(ACTIVE_FILTER_KEY, (AVAILABLE,)),
    ))

    assert manager.enrich_rows(context, rows) == rows
    assert rows[0][ACTIVE_FILTER_KEY] == AVAILABLE
    assert rows[1][ACTIVE_FILTER_KEY] == PARTIAL


def test_sitesync_filter_keys_remain_owned_when_provider_is_disabled():
    loader_controller = Mock()
    loader_controller.is_sitesync_enabled.return_value = False
    services = BrowserColumnServices(loader_controller)
    manager = BrowserColumnManager(
        services,
        [SiteSyncBrowserColumnProvider(loader_controller, services)],
        addon_manager=Mock(get_enabled_addons=lambda: []),
    )

    assert manager.get_columns(_context()) == []
    assert manager.get_filters(_context()) == []
    assert manager.get_filter_keys(_context()) == {
        ACTIVE_FILTER_KEY,
        REMOTE_FILTER_KEY,
    }
