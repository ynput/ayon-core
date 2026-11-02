from __future__ import annotations

from unittest.mock import Mock, patch

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


def _sitesync_addon(
    *,
    enabled: bool = True,
    availability: dict[str, tuple[int, int]] | None = None,
) -> Mock:
    addon = Mock()
    addon.enabled = enabled
    addon.DEFAULT_SITE = "studio"
    addon.is_project_enabled.return_value = enabled
    addon.get_active_site.return_value = "local"
    addon.get_remote_site.return_value = "studio"
    addon.get_provider_for_site.return_value = "local_drive"
    addon.get_site_icons.return_value = {}
    addon.get_version_availability.return_value = availability or {}
    return addon


def _sitesync_provider(
    services: BrowserColumnServices,
    sitesync_addon: Mock,
) -> SiteSyncBrowserColumnProvider:
    with patch(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager"
    ) as addons_manager:
        addons_manager.return_value.get.return_value = sitesync_addon
        return SiteSyncBrowserColumnProvider(services)


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
                options=["Keep"],
            )
        ]

    def get_required_query_keys(self, context):
        return {"status"}

    def enrich_rows(self, context, rows):
        self.enrich_calls += 1
        for row in rows:
            row["test:value"] = row["id"]
            row["test:status"] = row.get("status")


def test_provider_filter_requests_enrichment_when_column_is_hidden():
    provider = _TestProvider()
    manager = BrowserColumnManager(
        [provider],
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
    sitesync_addon = _sitesync_addon(availability={
        "version_a": (2, 1),
        "version_b": (1, 3),
    })
    loader_controller = Mock()
    loader_controller.get_versions_representation_count.return_value = {
        "version_a": 2,
        "version_b": 4,
    }
    services = BrowserColumnServices(loader_controller)
    provider = _sitesync_provider(services, sitesync_addon)
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

    sitesync_addon.get_version_availability.assert_called_once_with(
        "test",
        {"version_a", "version_b"},
        "local",
        "studio",
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
    sitesync_addon = _sitesync_addon(availability={
        "version_a": (2, 0),
        "version_b": (1, 0),
    })
    loader_controller = Mock()
    loader_controller.get_versions_representation_count.return_value = {
        "version_a": 2,
        "version_b": 4,
    }
    services = BrowserColumnServices(loader_controller)
    provider = _sitesync_provider(services, sitesync_addon)
    manager = BrowserColumnManager(
        [provider],
    )
    rows = [{"id": "version_a"}, {"id": "version_b"}]
    context = _context(filters=(
        BrowserFilter(ACTIVE_FILTER_KEY, (AVAILABLE,)),
    ))

    assert manager.enrich_rows(context, rows) == rows
    assert rows[0][ACTIVE_FILTER_KEY] == AVAILABLE
    assert rows[1][ACTIVE_FILTER_KEY] == PARTIAL


def test_sitesync_filter_keys_remain_owned_when_provider_is_disabled():
    services = BrowserColumnServices(Mock())
    manager = BrowserColumnManager(
        [_sitesync_provider(services, _sitesync_addon(enabled=False))],
    )

    assert manager.get_columns(_context()) == []
    assert manager.get_filters(_context()) == []
    assert manager.get_filter_keys(_context()) == {
        ACTIVE_FILTER_KEY,
        REMOTE_FILTER_KEY,
    }


class _ColumnOnlyProvider(BrowserColumnProvider):
    identifier = "column_only"
    column_keys = frozenset({"other:value"})

    def __init__(self) -> None:
        self.enrich_calls = 0

    def get_columns(self, context):
        return [TableColumn("other:value", "Other Value")]

    def enrich_rows(self, context, rows):
        self.enrich_calls += 1


def _status_rows() -> list[dict]:
    return [
        {"id": "v1", "status": "Keep"},
        {"id": "v2", "status": "Drop"},
        {"id": "v3", "status": None},
    ]


def test_filter_rows_skips_providers_without_active_filter():
    provider = _TestProvider()
    manager = BrowserColumnManager([provider])
    rows = _status_rows()

    # A visible column alone does not need the rows filtered.
    context = _context(enabled={"test:value"})

    assert manager.get_filtering_providers(context) == []
    assert manager.filter_rows(context, rows) is rows
    assert provider.enrich_calls == 0


def test_filter_rows_applies_only_provider_filters():
    provider = _TestProvider()
    column_provider = _ColumnOnlyProvider()
    manager = BrowserColumnManager([provider, column_provider])
    enriched_contexts = []
    original_enrich = provider.enrich_rows

    def enrich_rows(context, rows):
        enriched_contexts.append(context)
        original_enrich(context, rows)

    provider.enrich_rows = enrich_rows
    context = _context(
        enabled={"other:value"},
        filters=(
            BrowserFilter("test:status", ("Keep",)),
            # Applied by the server, not by the providers.
            BrowserFilter("status", ("Drop",)),
        ),
    )

    assert manager.get_filtering_providers(context) == [provider]
    rows = manager.filter_rows(context, _status_rows())

    assert [row["id"] for row in rows] == ["v1"]
    # Providers owning only a visible column are not called.
    assert column_provider.enrich_calls == 0
    assert enriched_contexts[0].enabled_column_keys == frozenset()


def test_filter_rows_supports_exclude_and_empty_values():
    manager = BrowserColumnManager([_TestProvider()])

    excluded = manager.filter_rows(
        _context(filters=(
            BrowserFilter("test:status", ("Keep",), exclude=True),
        )),
        _status_rows(),
    )
    without_value = manager.filter_rows(
        _context(filters=(BrowserFilter("test:status", ("noValue",)),)),
        _status_rows(),
    )

    assert [row["id"] for row in excluded] == ["v2", "v3"]
    assert [row["id"] for row in without_value] == ["v3"]


def test_filter_rows_ignores_filters_not_offered():
    provider = _TestProvider()
    provider.get_filters = lambda context: []
    manager = BrowserColumnManager([provider])
    rows = _status_rows()

    filtered = manager.filter_rows(
        _context(filters=(BrowserFilter("test:status", ("Keep",)),)),
        rows,
    )

    # Like the table, a filter the provider does not offer is ignored.
    assert filtered == rows
    assert provider.enrich_calls == 0


def test_filter_query_keys_only_of_filtering_providers():
    manager = BrowserColumnManager([_TestProvider()])

    # The provider's column is visible, but its filter is not active.
    assert manager.get_filter_query_keys(
        _context(enabled={"test:value"})
    ) == set()
    assert manager.get_filter_query_keys(
        _context(filters=(BrowserFilter("test:status", ("Keep",)),))
    ) == {"status"}
