"""Unit tests for PaginatedTableModel async request-id behaviour."""

from __future__ import annotations

import time as _time

import pytest
from ayon_core.ui.components.table_model import PaginatedTableModel


def test_request_id_rotates_on_model_resets() -> None:
    """A new request id is generated for each reset entrypoint."""

    def fetch_page(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None,
    ) -> list[dict[str, str]]:  # noqa: ARG001
        return []

    model = PaginatedTableModel(fetch_page=fetch_page, no_async=True)

    request_id = model._request_id  # type: ignore[attr-defined]

    model.reset_data()
    request_id_after_reset = model._request_id  # type: ignore[attr-defined]
    assert request_id_after_reset != request_id

    model.set_page(0)
    request_id_after_set_page = model._request_id  # type: ignore[attr-defined]
    assert request_id_after_set_page != request_id_after_reset


@pytest.mark.filterwarnings(
    "ignore::RuntimeWarning"
)  # Suppress expected warnings from test
def test_stale_results_discarded_after_reset(qtbot) -> None:
    """Results from a pre-reset fetch are discarded by request-id mismatch."""

    state = {"call_count": 0, "barrier": False}
    rows = [{"id": "item_001", "name": "Item 001"}]

    def slow_fetch_page(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None,
    ) -> list[dict[str, str]]:  # noqa: ARG001
        state["call_count"] += 1
        if page == 0 and not state["barrier"]:
            deadline = _time.monotonic() + 5.0
            while not state["barrier"] and _time.monotonic() < deadline:
                _time.sleep(0.01)
        return rows[:page_size]

    model = PaginatedTableModel(fetch_page=slow_fetch_page, page_size=50)

    qtbot.waitUntil(lambda: state["call_count"] >= 1, timeout=3000)

    model.reset_data()

    state["barrier"] = True

    qtbot.waitUntil(lambda: not model.is_loading, timeout=5000)

    assert model.rowCount() == 1
