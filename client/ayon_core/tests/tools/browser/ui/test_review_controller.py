from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.sitesync_columns import ACTIVE_FILTER_KEY
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

    rows = controller._fetch_product_group_headers()

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
