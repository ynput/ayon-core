from ayon_ui_qt.components.table_model import BatchFetchRequest

from ayon_core.tools.loader.ui.review_controller import ReviewController


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


def test_fetch_product_group_headers_fetches_all_pages_and_deduplicates(
    monkeypatch,
):
    controller = ReviewController()
    controller._current_project = "test_project"
    controller._selected_folder_id = "folder_A"

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
        "grp:Product:prod_1",
        "grp:Product:prod_2",
        "grp:Product:prod_3",
    ]
    assert [row["product/version"] for row in rows] == [
        "Product 1",
        "Product 2",
        "Product 3",
    ]


def test_fetch_versions_page_batch_page_zero_prepends_folders_and_tracks_cursors(
    monkeypatch,
):
    controller = ReviewController()
    controller._current_project = "test_project"
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
    ):
        calls.append((folder_id, cursor))
        return (
            [{"node": {"id": f"version:{folder_id}"}}],
            {
                "hasNextPage": True,
                "endCursor": f"cursor:{folder_id}",
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
    controller = ReviewController()
    controller._current_project = "test_project"
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
    ):
        calls.append((folder_id, cursor))
        return (
            [{"node": {"id": f"version:{folder_id}:page1"}}],
            {
                "hasNextPage": False,
                "endCursor": f"cursor:{folder_id}:next",
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
