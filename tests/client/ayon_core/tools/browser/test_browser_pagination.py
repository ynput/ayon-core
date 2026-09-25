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
    assert get_sort_by("product/version", options) == "path"
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
