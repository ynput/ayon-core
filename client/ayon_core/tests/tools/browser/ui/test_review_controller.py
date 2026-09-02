from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.sitesync_columns import ACTIVE_FILTER_KEY
from ayon_core.tools.browser.ui.browser_group_by import (
    GROUP_BY_PRODUCT_KEY,
    GROUP_BY_STATUS_KEY,
    GROUP_BY_TAGS_KEY,
    build_attribute_groups,
)
from ayon_core.tools.browser.view_defaults import BROWSER_VIEW_DEFAULTS
from ayon_core.ui.components.table_filter import FilterCriterion
from ayon_core.ui.components.table_model import BatchFetchRequest

from ayon_core.tools.browser.ui.browser_controller import BrowserController
from ayon_core.tools.browser.control import LoaderController


@pytest.fixture(autouse=True)
def _mock_sitesync_model(monkeypatch):
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = []
    monkeypatch.setattr(
        "ayon_core.tools.browser.control.AddonsManager",
        lambda: addon_manager,
    )
    monkeypatch.setattr(
        "ayon_core.tools.browser.control.SiteSyncModel",
        lambda *args: Mock(),
    )


def _make_request(
    parent_id: str | None,
    page: int,
    page_size: int = 25,
    sort_key: str | None = None,
    descending: bool = False,
) -> BatchFetchRequest:
    return BatchFetchRequest(
        page=page,
        page_size=page_size,
        sort_key=sort_key,
        descending=descending,
        parent_id=parent_id,
    )


def test_extension_filter_is_not_forwarded_to_graphql():
    controller = BrowserController(LoaderController())
    controller.set_filter_criteria([
        FilterCriterion(
            key=ACTIVE_FILTER_KEY,
            attribute_label="Active Site",
            values=["Available"],
        )
    ])

    assert controller._get_query_filters()["version_filter"] == ""


def test_controller_uses_browser_view_defaults():
    controller = BrowserController(LoaderController())
    defaults = BROWSER_VIEW_DEFAULTS

    assert controller.group_by_key == defaults.group_by_key
    assert controller.tree_mode is False
    assert controller.hide_empty_groups is not defaults.show_empty_groups
    assert (
        controller.include_folder_children
        is defaults.include_children
    )
    assert controller.featured_version_order == list(
        defaults.featured_version_order
    )
    assert controller.latest_per_folder is defaults.latest_per_folder


def test_fetch_product_group_headers_fetches_all_pages_and_deduplicates(
    monkeypatch,
):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["folder_A"]

    calls: list[str | None] = []

    def fake_get_products_page(
        project_name,
        folder_id,
        page_size,
        cursor=None,
        sort_by=None,
        descending=False,
        folder_ids=None,
        product_filter="",
        **kwargs,
    ):
        calls.append(cursor)
        if cursor is None:
            return (
                [
                    {
                        "node": {
                            "id": "prod_1",
                            "name": "Product 1",
                            "productType": "render",
                        }
                    },
                    {
                        "node": {
                            "id": "prod_2",
                            "name": "Product 2",
                            "productType": "plate",
                        }
                    },
                ],
                {"hasNextPage": True, "endCursor": "cursor_1"},
            )
        return (
            [
                {
                    "node": {
                        "id": "prod_2",
                        "name": "Product 2",
                        "productType": "plate",
                    }
                },
                {
                    "node": {
                        "id": "prod_3",
                        "name": "Product 3",
                        "productType": "render",
                    }
                },
            ],
            {"hasNextPage": False, "endCursor": "cursor_2"},
        )

    monkeypatch.setattr(
        controller, "_get_products_page", fake_get_products_page
    )

    rows = controller._fetch_product_group_headers({
        "prod_1": 2,
        "prod_2": 3,
        "prod_3": 1,
    })

    assert calls == [None, "cursor_1"]
    assert [row["id"] for row in rows] == [
        "grp:product:prod_1",
        "grp:product:prod_2",
        "grp:product:prod_3",
    ]
    assert [row["product/version"] for row in rows] == [
        "Product 1",
        "Product 2",
        "Product 3",
    ]
    assert [row["child_count"] for row in rows] == [2, 3, 1]


def test_fetch_versions_page_prepends_folders_and_tracks_cursors(
    monkeypatch,
):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["A", "B"]
    controller._include_folder_children = False
    controller._folder_cursors = {"A": "stale", "B": "stale"}
    controller._folder_has_more = {"A": True, "B": True}

    calls: list[tuple[str, str]] = []

    def fake_get_child_folder_rows(parent_id: str):
        return [{"id": f"folder:{parent_id}", "has_children": True}]

    def fake_get_versions_page(
        project_name,
        folder_id,
        page_size,
        cursor=None,
        sort_by=None,
        descending=False,
        version_ids=None,
        include_folder_children=True,
        folder_ids=None,
        product_ids=None,
        version_filter="",
        product_filter="",
        **kwargs,
    ):
        calls.append((folder_ids[0], cursor))
        return (
            [{"node": {"id": f"version:{folder_ids[0]}"}}],
            {
                "hasNextPage": True,
                "endCursor": f"cursor:{folder_ids[0]}",
                "hasPreviousPage": False,
                "startCursor": "",
            },
        )

    monkeypatch.setattr(
        controller, "_get_child_folder_rows", fake_get_child_folder_rows
    )
    monkeypatch.setattr(
        controller, "_get_versions_page", fake_get_versions_page
    )
    monkeypatch.setattr(
        controller,
        "_transform_version_edge",
        lambda edge: {"id": edge["node"]["id"]},
    )

    result = controller.fetch_versions_page_batch(
        [_make_request("A", 0), _make_request("B", 0)]
    )

    assert calls == [("A", ""), ("B", "")]
    assert result["A"] == [
        {"id": "folder:A", "has_children": True},
        {"id": "version:A"},
    ]
    assert result["B"] == [
        {"id": "folder:B", "has_children": True},
        {"id": "version:B"},
    ]
    assert controller._folder_cursors == {"A": "cursor:A", "B": "cursor:B"}
    assert controller._folder_has_more == {"A": True, "B": True}


def test_fetch_versions_page_batch_continuation_uses_each_parent_cursor(
    monkeypatch,
):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["A", "B"]
    controller._folder_cursors = {"A": "cursor:A", "B": "cursor:B"}
    controller._folder_has_more = {"A": True, "B": False}

    calls: list[tuple[str, str]] = []

    def fake_get_versions_page(
        project_name,
        folder_id,
        page_size,
        cursor=None,
        sort_by=None,
        descending=False,
        version_ids=None,
        include_folder_children=True,
        folder_ids=None,
        product_ids=None,
        version_filter="",
        product_filter="",
        **kwargs,
    ):
        calls.append((folder_ids[0], cursor))
        return (
            [{"node": {"id": f"version:{folder_ids[0]}:page1"}}],
            {
                "hasNextPage": False,
                "endCursor": f"cursor:{folder_ids[0]}:next",
                "hasPreviousPage": False,
                "startCursor": "",
            },
        )

    monkeypatch.setattr(
        controller, "_get_versions_page", fake_get_versions_page
    )
    monkeypatch.setattr(
        controller,
        "_transform_version_edge",
        lambda edge: {"id": edge["node"]["id"]},
    )

    result = controller.fetch_versions_page_batch(
        [_make_request("A", 1), _make_request("B", 1)]
    )

    assert calls == [("A", "cursor:A")]
    assert result["A"] == [{"id": "version:A:page1"}]
    assert result["B"] == []
    assert controller._folder_cursors["A"] == "cursor:A:next"
    assert controller._folder_has_more["A"] is False


def test_group_counts_use_filtered_distribution(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["folder_A"]
    connection = Mock()
    connection.query_graphql.return_value = SimpleNamespace(
        errors=None,
        data={
            "data": {
                "project": {
                    "versions": {
                        "fieldStats": [{
                            "columnName": "tags",
                            "valueFilledCount": 3,
                            "valueNotFilledCount": 0,
                            "distribution": [
                                {
                                    "value": ["Animation", "Review"],
                                    "count": 2,
                                },
                                {
                                    "value": ["Animation"],
                                    "count": 1,
                                },
                            ],
                        }]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller."
        "ayon_api.get_server_api_connection",
        lambda: connection,
    )

    counts = controller._get_group_counts(
        controller._group_by_options[GROUP_BY_TAGS_KEY]
    )

    assert counts == {"Animation": 3, "Review": 2}
    variables = connection.query_graphql.call_args.args[1]
    assert variables["folderIds"] == ["folder_A"]
    assert variables["targets"] == [{
        "field": "tags",
        "aggregations": ["DISTRIBUTION", "FILLED", "NOT_FILLED"],
    }]


def test_product_group_counts_normalize_uuid_values(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["folder_A"]
    connection = Mock()
    connection.query_graphql.return_value = SimpleNamespace(
        errors=None,
        data={
            "data": {
                "project": {
                    "versions": {
                        "fieldStats": [{
                            "columnName": "product_id",
                            "valueFilledCount": 1,
                            "valueNotFilledCount": 0,
                            "distribution": [{
                                "value": (
                                    "6c035657-168d-11f1-aa74-60cf848a5b16"
                                ),
                                "count": 1,
                            }],
                        }]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller."
        "ayon_api.get_server_api_connection",
        lambda: connection,
    )

    counts = controller._get_group_counts(
        controller._group_by_options[GROUP_BY_PRODUCT_KEY]
    )

    assert counts == {
        "6c035657168d11f1aa7460cf848a5b16": 1,
    }


def test_group_counts_control_empty_status_rows(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["folder_A"]
    controller._group_by_key = GROUP_BY_STATUS_KEY
    controller._project_info = {
        "by_name": {
            "statuses": {
                "Done": {"icon": "check", "color": "#00ff00"},
                "Blocked": {"icon": "block", "color": "#ff0000"},
            }
        }
    }
    monkeypatch.setattr(
        controller,
        "_get_group_counts",
        lambda _group: {"Done": 4},
    )
    monkeypatch.setattr(
        controller,
        "_get_group_inventory_counts",
        lambda _group: {"Done": 10, "Blocked": 5},
    )

    controller._hide_empty_groups = True
    rows = controller._fetch_group_headers()

    assert [row["product/version"] for row in rows] == ["Done"]
    assert rows[0]["child_count"] == 4
    assert rows[0]["has_children"] is True

    controller._hide_empty_groups = False
    rows = controller._fetch_group_headers()
    rows_by_name = {row["product/version"]: row for row in rows}

    assert set(rows_by_name) == {"Done", "Blocked"}
    assert rows_by_name["Blocked"]["child_count"] == 0
    assert rows_by_name["Blocked"]["has_children"] is False


def test_missing_filtered_counts_keep_product_groups_expandable(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._selected_folder_ids = ["folder_A"]
    controller._group_by_key = GROUP_BY_PRODUCT_KEY
    monkeypatch.setattr(
        controller,
        "_get_group_counts",
        lambda _group: None,
    )
    monkeypatch.setattr(
        controller,
        "_get_group_inventory_counts",
        lambda _group: {},
    )
    monkeypatch.setattr(
        controller,
        "_fetch_product_group_headers",
        lambda counts: [{
            "counts": counts,
            "has_children": counts is None,
        }],
    )

    rows = controller._fetch_group_headers()

    assert rows == [{"counts": None, "has_children": True}]


def test_missing_filtered_counts_fall_back_to_group_inventory(monkeypatch):
    controller = BrowserController(LoaderController())
    controller._current_project = "test_project"
    controller._group_by_key = GROUP_BY_STATUS_KEY
    controller._hide_empty_groups = True
    controller._project_info = {
        "by_name": {
            "statuses": {
                "Done": {"icon": "check", "color": "#00ff00"},
                "Blocked": {"icon": "block", "color": "#ff0000"},
            }
        }
    }
    monkeypatch.setattr(
        controller,
        "_get_group_counts",
        lambda _group: None,
    )
    monkeypatch.setattr(
        controller,
        "_get_group_inventory_counts",
        lambda _group: {"Done": 3, "Blocked": 0},
    )

    rows = controller._fetch_group_headers()

    assert [row["product/version"] for row in rows] == ["Done"]
    assert rows[0]["child_count"] == 3
    assert rows[0]["has_children"] is True


def test_attribute_grouping_only_exposes_scalar_types():
    options = build_attribute_groups({
        "approved": {"type": "boolean"},
        "priority": {"type": "integer"},
        "department": {"type": "string"},
        "reviewers": {"type": "list_of_strings"},
        "metadata": {"type": "dict"},
    })

    assert [option.attribute_name for option in options] == [
        "approved",
        "priority",
        "department",
    ]


def test_boolean_attribute_group_uses_scalar_equality():
    controller = BrowserController(LoaderController())
    controller._version_attributes = {
        "approved": {"type": "boolean"}
    }

    version_filter, product_filter = controller._build_version_filter(
        "attr:approved",
        "true",
    )

    assert product_filter == ""
    assert version_filter == (
        '{"conditions": [{"key": "attrib.approved", '
        '"value": true, "operator": "eq"}]}'
    )
