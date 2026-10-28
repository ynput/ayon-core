"""Tests for resolving the versions of Browser group headers."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from ayon_core.tools.browser.columns import (
    BrowserColumnContext,
    BrowserColumnManager,
    BrowserColumnProvider,
    BrowserFilter,
)
from ayon_core.tools.browser.ui import browser_controller
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_group_by import (
    GROUP_BY_PRODUCT_KEY,
    GROUP_BY_STATUS_KEY,
)
from ayon_core.ui.components.table_model import (
    FilterEntry,
    PaginatedTableModel,
)


class FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = {"data": data}
        self.errors = None


class FakeConnection:
    """Serve version ids in pages, like the versions resolver."""

    def __init__(self, version_ids: list[str]) -> None:
        self.version_ids = version_ids
        self.calls: list[dict[str, Any]] = []

    def query_graphql(
        self, query: str, variables: dict[str, Any]
    ) -> FakeResponse:
        self.calls.append(dict(variables))
        start = int(variables["after"] or 0)
        end = start + variables["first"]
        page = self.version_ids[start:end]
        return FakeResponse({
            "project": {
                "versions": {
                    "pageInfo": {
                        "endCursor": str(end) if page else None,
                        "hasNextPage": end < len(self.version_ids),
                    },
                    "edges": [
                        {"node": {"id": version_id}}
                        for version_id in page
                    ],
                }
            }
        })


class ControllerStub:
    """Just enough of the controller to resolve group versions."""

    _parse_group_id = staticmethod(BrowserWidgetController._parse_group_id)
    _merge_query_filters = staticmethod(
        BrowserWidgetController._merge_query_filters
    )
    _version_filter_variables = staticmethod(
        BrowserWidgetController._version_filter_variables
    )
    _get_group_versions_filter = (
        BrowserWidgetController._get_group_versions_filter
    )
    _build_version_filter = BrowserWidgetController._build_version_filter
    _version_query_kwargs = BrowserWidgetController._version_query_kwargs
    get_group_version_ids = BrowserWidgetController.get_group_version_ids

    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)
        self._current_project = "project"
        self._selected_folder_ids = ["folder_a"]
        self._include_folder_children = True
        self._latest_per_folder = False
        self._group_by_key = GROUP_BY_STATUS_KEY
        self._group_by_options: dict[str, Any] = {}
        self._column_manager = BrowserColumnManager()
        self._active_filters: tuple[BrowserFilter, ...] = ()

    def _get_column_context(self) -> BrowserColumnContext:
        return BrowserColumnContext(
            project_name=self._current_project,
            category="hierarchy",
            selected_folder_ids=tuple(self._selected_folder_ids),
            selected_task_ids=(),
            enabled_column_keys=frozenset(),
            active_filters=self._active_filters,
            group_by_key=self._group_by_key,
            include_folder_children=self._include_folder_children,
        )

    def _get_query_filters(self) -> dict[str, Any]:
        return {
            "version_filter": json.dumps({
                "conditions": [
                    {"key": "author", "value": "me", "operator": "eq"}
                ]
            }),
            "product_filter": "",
            "task_filter": "",
            "folder_filter": "",
            "representation_filter": "",
            "featured_only": None,
            "search": None,
            "has_reviewables": None,
        }


@pytest.fixture
def connection(monkeypatch) -> FakeConnection:
    con = FakeConnection([f"v{idx}" for idx in range(5)])
    monkeypatch.setattr(
        browser_controller.ayon_api,
        "get_server_api_connection",
        lambda: con,
    )
    monkeypatch.setattr(
        browser_controller, "get_version_ids_query", lambda: "query"
    )
    monkeypatch.setattr(browser_controller, "_VERSION_IDS_PAGE_SIZE", 2)
    return con


def test_group_version_ids_follow_all_pages(connection) -> None:
    controller = ControllerStub()

    version_ids = controller.get_group_version_ids(
        f"grp:{GROUP_BY_STATUS_KEY}:Approved"
    )

    assert version_ids == {f"v{idx}" for idx in range(5)}
    assert [call["after"] for call in connection.calls] == [None, "2", "4"]
    variables = connection.calls[0]
    assert variables["folderIds"] == ["folder_a"]
    assert variables["includeFolderChildren"] is True
    assert variables["productIds"] is None
    # The active filters are kept and narrowed down to the group.
    conditions = json.loads(variables["versionFilter"])["conditions"]
    assert {"key": "author", "value": "me", "operator": "eq"} in conditions
    assert {
        "key": "status", "value": ["Approved"], "operator": "in"
    } in conditions


def test_product_group_versions_use_product_ids(connection) -> None:
    controller = ControllerStub()

    controller.get_group_version_ids(f"grp:{GROUP_BY_PRODUCT_KEY}:prod_1")

    assert connection.calls[0]["productIds"] == ["prod_1"]


def test_group_without_versions_does_not_query(connection) -> None:
    controller = ControllerStub()

    # The group of versions without a value, of an unknown axis.
    version_ids = controller.get_group_version_ids("grp:attr:unknown")

    assert version_ids == set()
    assert connection.calls == []


class InSceneStubProvider(BrowserColumnProvider):
    """Mark versions in the scene, like the In Scene column."""

    identifier = "in_scene_stub"
    column_keys = frozenset({"in_scene"})
    filter_keys = frozenset({"in_scene"})

    def __init__(self, loaded_ids: set[str]) -> None:
        self.loaded_ids = loaded_ids
        self.enriched: list[list[dict[str, Any]]] = []

    def get_filters(self, context: BrowserColumnContext) -> list[FilterEntry]:
        return [FilterEntry("in_scene", "In Scene", options=["Yes", "No"])]

    def enrich_rows(
        self, context: BrowserColumnContext, rows: list[dict[str, Any]]
    ) -> None:
        self.enriched.append([dict(row) for row in rows])
        for row in rows:
            if row.get("entityType") == "Version":
                in_scene = row["id"] in self.loaded_ids
                row["in_scene"] = "Yes" if in_scene else "No"


def test_group_version_ids_skip_providers_without_filter(connection) -> None:
    controller = ControllerStub()
    provider = InSceneStubProvider({"v1"})
    controller._column_manager = BrowserColumnManager([provider])

    version_ids = controller.get_group_version_ids(
        f"grp:{GROUP_BY_STATUS_KEY}:Approved"
    )

    assert version_ids == {f"v{idx}" for idx in range(5)}
    assert provider.enriched == []


def test_group_version_ids_apply_provider_filters(connection) -> None:
    controller = ControllerStub()
    provider = InSceneStubProvider({"v1", "v4"})
    controller._column_manager = BrowserColumnManager([provider])
    controller._active_filters = (BrowserFilter("in_scene", ("Yes",)),)

    version_ids = controller.get_group_version_ids(
        f"grp:{GROUP_BY_STATUS_KEY}:Approved"
    )

    assert version_ids == {"v1", "v4"}
    # Each page of ids is checked by the provider as version rows.
    assert provider.enriched == [
        [
            {"id": "v0", "entityType": "Version"},
            {"id": "v1", "entityType": "Version"},
        ],
        [
            {"id": "v2", "entityType": "Version"},
            {"id": "v3", "entityType": "Version"},
        ],
        [{"id": "v4", "entityType": "Version"}],
    ]


def _make_model(children: dict[str, list[dict[str, Any]]]):
    def fetch_page(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None,
    ) -> list[dict[str, Any]]:
        if parent_id is None:
            rows = [
                {"id": group_id, "has_children": True}
                for group_id in children
            ]
        else:
            rows = children[parent_id]
        return rows[page * page_size:(page + 1) * page_size]

    model = PaginatedTableModel(
        fetch_page=fetch_page, page_size=2, no_async=True
    )
    model.set_tree_mode(True)
    return model


def _group_index(model: PaginatedTableModel, group_id: str):
    for node in model._root.children:  # type: ignore[attr-defined]
        if node.node_id == group_id:
            return model._index_for_node(node)  # type: ignore[attr-defined]
    raise AssertionError(f"Missing group row {group_id}")


def test_all_child_rows_only_when_fully_loaded(qtbot) -> None:
    children = {
        "grp:a": [{"id": "v1"}],
        "grp:b": [{"id": "v2"}, {"id": "v3"}, {"id": "v4"}],
        "grp:c": [{"id": "v5"}],
    }
    model = _make_model(children)

    # Not expanded yet.
    assert model.get_all_child_rows("grp:a") is None

    model.fetchMore(_group_index(model, "grp:a"))
    assert model.get_all_child_rows("grp:a") == [{"id": "v1"}]

    # Only the first page of a larger group is loaded.
    model.fetchMore(_group_index(model, "grp:b"))
    assert model.get_all_child_rows("grp:b") is None
    model.fetchMore(_group_index(model, "grp:b"))
    assert model.get_all_child_rows("grp:b") == children["grp:b"]

    assert model.get_all_child_rows("grp:c") is None
    assert model.get_all_child_rows("grp:missing") is None


def test_all_child_rows_leave_out_rejected_rows(qtbot) -> None:
    children = {"grp:a": [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]}
    model = _make_model(children)
    model.fetchMore(_group_index(model, "grp:a"))
    model.fetchMore(_group_index(model, "grp:a"))
    calls = []

    def accept_row(row: int, parent_index) -> bool:
        calls.append((row, parent_index.internalPointer().node_id))
        return row != 1

    rows = model.get_all_child_rows("grp:a", accept_row=accept_row)

    assert rows == [{"id": "v1"}, {"id": "v3"}]
    # Called with the child rows under the parent's index, like the
    # table filter's `filterAcceptsRow`.
    assert calls == [(0, "grp:a"), (1, "grp:a"), (2, "grp:a")]
