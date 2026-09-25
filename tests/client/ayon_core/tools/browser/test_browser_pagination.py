"""Tests for sorted, cursor based pagination of the Browser versions."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from ayon_core.tools.browser.server_capabilities import (
    parse_sort_by_options,
)
from ayon_core.tools.browser.ui import browser_queries
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_group_by import GROUP_BY_NONE_KEY
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory


class FakeVersionsServer:
    """Mimic the cursor pagination of the AYON server versions resolver.

    Like the server, ``last``/``before`` pages are ordered descending
    and returned in that order (not reversed), so ``startCursor`` is the
    highest row of the page and ``endCursor`` the lowest one.
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def get_versions_page(
        self,
        project_name: str,
        folder_id: str | None,
        page_size: int,
        cursor: str | None = None,
        sort_by: str | None = None,
        descending: bool = False,
        folder_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.calls.append({
            "cursor": cursor,
            "sort_by": sort_by,
            "descending": descending,
            "folder_ids": folder_ids,
        })
        rows = [
            row for row in self.rows
            if folder_ids is None or row["folderId"] in folder_ids
        ]
        # Sort column first, creation order as the tie breaker.
        sort_column = sort_by or "creationOrder"

        def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
            return (row[sort_column], row["creationOrder"])

        rows.sort(key=sort_key, reverse=descending)
        if cursor:
            cursor_value = tuple(cursor.split("|"))
            cursor_value = (
                type(rows[0][sort_column])(cursor_value[0]),
                int(cursor_value[1]),
            )
            if descending:
                rows = [r for r in rows if sort_key(r) < cursor_value]
            else:
                rows = [r for r in rows if sort_key(r) > cursor_value]
        page = rows[:page_size]
        edges = [
            {
                "cursor": f"{row[sort_column]}|{row['creationOrder']}",
                "node": row,
            }
            for row in page
        ]
        has_more = len(page) >= page_size
        page_info = {
            "startCursor": edges[0]["cursor"] if edges else None,
            "endCursor": edges[-1]["cursor"] if edges else None,
            "hasNextPage": has_more and not descending,
            "hasPreviousPage": has_more and descending,
        }
        return edges, page_info


class ControllerStub:
    """Just enough of the controller to run its version pagination."""

    _page_cursor = staticmethod(BrowserWidgetController._page_cursor)
    _page_key = BrowserWidgetController._page_key
    _get_page_cursor = BrowserWidgetController._get_page_cursor
    _store_next_page_cursor = BrowserWidgetController._store_next_page_cursor
    _reset_pagination = BrowserWidgetController._reset_pagination
    _fetch_versions_page_base = (
        BrowserWidgetController._fetch_versions_page_base
    )

    def __init__(self, server: FakeVersionsServer) -> None:
        self.log = logging.getLogger(__name__)
        self._server = server
        self._current_project = "project"
        self._current_category = BrowserSlicerCategory.HIERARCHY.value
        self._selected_folder_ids = ["folder_a", "folder_b"]
        self._include_folder_children = False
        self._tree_mode = False
        self._review_session_version_ids = None
        self._page_cursors: dict[tuple[Any, ...], str] = {}
        self._pagination_generation = 0

    @property
    def group_by_key(self) -> str:
        return GROUP_BY_NONE_KEY

    def _get_query_filters(self) -> dict[str, Any]:
        return {}

    def _version_query_kwargs(self, *args: Any) -> dict[str, Any]:
        return {}

    def _get_versions_page(self, *args: Any, **kwargs: Any):
        return self._server.get_versions_page(*args, **kwargs)

    @staticmethod
    def _transform_version_edge(edge: dict[str, Any]) -> dict[str, Any]:
        return edge["node"]


def _make_rows() -> list[dict[str, Any]]:
    """Versions of two folders, created interleaved."""
    rows = []
    for index in range(23):
        rows.append({
            "id": f"version_{index}",
            "folderId": "folder_a" if index % 2 else "folder_b",
            "creationOrder": index,
            # Not in creation order, and with ties.
            "createdAt": f"2026-01-{(index * 7) % 11 + 1:02}",
        })
    return rows


def _fetch_all(
    controller: ControllerStub,
    sort_key: str | None,
    descending: bool,
    page_size: int = 5,
) -> list[dict[str, Any]]:
    output = []
    for page_number in range(100):
        page = controller._fetch_versions_page_base(
            page_number, page_size, sort_key, descending
        )
        if not page:
            break
        output.extend(page)
    return output


@pytest.mark.unit
@pytest.mark.parametrize("descending", [False, True])
def test_pages_of_multiple_folders_are_sorted(descending: bool) -> None:
    """All pages together list every version exactly once, in order."""
    rows = _make_rows()
    server = FakeVersionsServer(rows)
    controller = ControllerStub(server)

    fetched = _fetch_all(controller, "createdAt", descending)

    expected = sorted(
        rows,
        key=lambda r: (r["createdAt"], r["creationOrder"]),
        reverse=descending,
    )
    assert [r["id"] for r in fetched] == [r["id"] for r in expected]
    assert all(
        call["folder_ids"] == ["folder_a", "folder_b"]
        for call in server.calls
    )


@pytest.mark.unit
def test_descending_page_continues_from_end_cursor() -> None:
    """Descending pages continue from the lowest row of the last page."""
    page_info = {
        "startCursor": "highest",
        "endCursor": "lowest",
        "hasNextPage": False,
        "hasPreviousPage": True,
    }
    assert BrowserWidgetController._page_cursor(page_info, True) == (
        True, "lowest"
    )


@pytest.mark.unit
def test_stale_page_of_other_sort_does_not_leak_cursor() -> None:
    """A late page of a previous sort must not affect the current one."""
    rows = _make_rows()
    server = FakeVersionsServer(rows)
    controller = ControllerStub(server)

    # New listing (descending) starts.
    first = controller._fetch_versions_page_base(0, 5, "createdAt", True)
    # A page of the previous (ascending) listing finishes late.
    controller._fetch_versions_page_base(0, 5, "createdAt", False)
    controller._fetch_versions_page_base(1, 5, "createdAt", False)
    second = controller._fetch_versions_page_base(1, 5, "createdAt", True)

    expected = sorted(
        rows,
        key=lambda r: (r["createdAt"], r["creationOrder"]),
        reverse=True,
    )
    assert [r["id"] for r in first + second] == [
        r["id"] for r in expected[:10]
    ]


@pytest.mark.unit
def test_reset_pagination_invalidates_running_listing() -> None:
    """After a reset only a new first page can be fetched."""
    server = FakeVersionsServer(_make_rows())
    controller = ControllerStub(server)

    controller._fetch_versions_page_base(0, 5, "createdAt", False)
    controller._reset_pagination()

    assert controller._fetch_versions_page_base(
        1, 5, "createdAt", False
    ) == []


@pytest.mark.unit
def test_parse_sort_by_options() -> None:
    assert parse_sort_by_options(
        "Sort by one of author, version, folderName, path"
    ) == frozenset({"author", "version", "folderName", "path"})
    assert parse_sort_by_options("") == frozenset()
    assert parse_sort_by_options("Something else") == frozenset()


@pytest.mark.unit
def test_get_sort_by() -> None:
    options = frozenset({"folderName", "productName"})
    get_sort_by = browser_queries.get_sort_by

    assert get_sort_by(None, options) is None
    assert get_sort_by("product/version", options) == "productName"
    assert get_sort_by("product/version", frozenset({"path"})) == "path"
    assert get_sort_by("createdAt", options) == "createdAt"
    assert get_sort_by("folderName", options) == "folderName"
    assert get_sort_by("productName", options) == "productName"
    # Known to the frontend, but not listed by this (older) server.
    assert get_sort_by("taskType", options) is None
    assert get_sort_by("attr:version:resolution", options) == (
        "attrib.resolution"
    )
    assert get_sort_by("attr:folder:resolution", options) is None
    assert get_sort_by("thumb", options) is None


@pytest.mark.unit
def test_get_product_sort_by() -> None:
    options = frozenset({"name", "path", "createdAt", "folderName"})
    get_product_sort_by = browser_queries.get_product_sort_by

    assert get_product_sort_by(None, options) is None
    assert get_product_sort_by("path", options) == "path"
    assert get_product_sort_by("productName", options) == "name"
    assert get_product_sort_by("createdAt", options) == "createdAt"
    assert get_product_sort_by("attrib.fps", options) == "attrib.fps"
    # Versions only, the products resolver does not list them.
    assert get_product_sort_by("author", options) is None
    assert get_product_sort_by("taskName", options) is None


class ProductGroupsStub:
    """Just enough of the controller to fetch the product group rows."""

    _page_cursor = staticmethod(BrowserWidgetController._page_cursor)
    _extract_product_group_data = staticmethod(
        BrowserWidgetController._extract_product_group_data
    )
    _fetch_product_group_headers = (
        BrowserWidgetController._fetch_product_group_headers
    )

    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)
        self._current_project = "project"
        self._selected_folder_ids = ["folder_a"]
        self._hide_empty_groups = False
        self._include_folder_children = False
        self._group_by_options = {"product": None}
        self.calls: list[dict[str, Any]] = []

    def _get_query_filters(self) -> dict[str, Any]:
        return {
            "product_filter": "",
            "version_filter": "",
            "task_filter": "",
            "folder_filter": "",
            "search": None,
        }

    def _get_products_page(self, *args: Any, **kwargs: Any):
        self.calls.append(kwargs)
        page_number = len(self.calls)
        edges = [{"node": {
            "id": f"product_{page_number}",
            "name": f"product_{page_number}",
            "productType": "model",
        }}]
        has_more = page_number < 2
        descending = kwargs["descending"]
        return edges, {
            "startCursor": f"start_{page_number}",
            "endCursor": f"end_{page_number}",
            "hasNextPage": has_more and not descending,
            "hasPreviousPage": has_more and descending,
        }

    def _product_appearance(self, *args: Any) -> tuple[str, str]:
        return "view_in_ar", "#fff"

    def _build_group_header_row(self, option: Any, **kwargs: Any):
        return {"id": kwargs["value"]}


@pytest.mark.unit
@pytest.mark.parametrize("descending", [False, True])
def test_product_group_headers_follow_table_sort(
    monkeypatch, descending: bool
) -> None:
    """Grouped by product, the product rows are sorted like the table."""
    monkeypatch.setattr(
        browser_queries,
        "get_server_products_sort_options",
        lambda: frozenset({"createdAt", "path"}),
    )
    controller = ProductGroupsStub()

    rows = controller._fetch_product_group_headers(
        None, "createdAt", descending
    )

    assert [row["id"] for row in rows] == ["product_1", "product_2"]
    assert [
        (call["sort_by"], call["descending"], call["cursor"])
        for call in controller.calls
    ] == [
        ("createdAt", descending, None),
        ("createdAt", descending, "end_1"),
    ]


@pytest.mark.unit
def test_product_group_headers_fall_back_to_path(monkeypatch) -> None:
    """A column products can't be sorted by keeps the path order."""
    monkeypatch.setattr(
        browser_queries,
        "get_server_products_sort_options",
        lambda: frozenset({"createdAt", "path"}),
    )
    controller = ProductGroupsStub()

    controller._fetch_product_group_headers(None, "author", True)

    assert (
        controller.calls[0]["sort_by"], controller.calls[0]["descending"]
    ) == ("path", False)
