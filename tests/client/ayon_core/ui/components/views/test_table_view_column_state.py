"""Tests for AYTableView column-state API."""

from __future__ import annotations

from typing import Any

import pytest

from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.views.data_models import ColumnState


_ROWS: list[dict[str, Any]] = [
    {"id": f"r{i}", "name": f"R{i}", "status": "ok", "version": f"v{i}"}
    for i in range(3)
]


def _fetch(page, page_size, sort_key, descending, parent_id):  # noqa: ANN001,ARG001,E501
    if page != 0:
        return []
    return list(_ROWS)


@pytest.fixture()
def view_and_model(qtbot):
    """Construct an AYTableView wired to a PaginatedTableModel."""
    cols = [
        TableColumn("name", "Name", width=100),
        TableColumn("status", "Status", width=80),
        TableColumn("version", "Version", width=60),
    ]
    model = PaginatedTableModel(
        fetch_page=_fetch,
        columns=cols,
        page_size=10,
        no_async=True,
    )
    view = AYTableView()
    qtbot.addWidget(view)
    view.setModel(model)
    return view, model


def test_get_column_state_initial_order_matches_model(view_and_model) -> None:
    """Initial state reflects model column order, all visible, no pin."""
    view, model = view_and_model
    states = view.get_column_state()
    assert [s.name for s in states] == ["name", "status", "version"]
    assert all(s.visible for s in states)
    assert not any(s.pinned for s in states)


def test_set_column_state_reorders_visually(view_and_model) -> None:
    """set_column_state moves header sections to the requested order."""
    view, model = view_and_model
    view.set_column_state(
        [
            ColumnState(name="version"),
            ColumnState(name="name"),
            ColumnState(name="status"),
        ]
    )
    states = view.get_column_state()
    assert [s.name for s in states] == ["version", "name", "status"]


def test_set_column_state_hides_columns(view_and_model) -> None:
    """Setting visible=False hides the corresponding section."""
    view, model = view_and_model
    view.set_column_state(
        [
            ColumnState(name="name"),
            ColumnState(name="status", visible=False),
            ColumnState(name="version"),
        ]
    )
    header = view.header()
    # logical index of "status" is still 1 in the model.
    assert header.isSectionHidden(1) is True
    states = view.get_column_state()
    by_name = {s.name: s for s in states}
    assert by_name["status"].visible is False


def test_set_column_state_resizes(view_and_model) -> None:
    """Width values are applied via resizeSection."""
    view, model = view_and_model
    view.set_column_state(
        [
            ColumnState(name="name", width=222),
            ColumnState(name="status"),
            ColumnState(name="version"),
        ]
    )
    header = view.header()
    assert header.sectionSize(0) == 222


def test_set_column_state_persists_pinned(view_and_model) -> None:
    """Pinned keys roundtrip through get/set_column_state."""
    view, model = view_and_model
    view.set_column_state(
        [
            ColumnState(name="name", pinned=True),
            ColumnState(name="status"),
            ColumnState(name="version", pinned=True),
        ]
    )
    pinned = {s.name for s in view.get_column_state() if s.pinned}
    assert pinned == {"name", "version"}


def test_column_state_changed_emitted_on_set(view_and_model, qtbot) -> None:
    """A single coalesced signal fires for a batched set_column_state."""
    view, model = view_and_model
    with qtbot.waitSignal(view.column_state_changed, timeout=1000) as blocker:
        view.set_column_state(
            [
                ColumnState(name="version"),
                ColumnState(name="status"),
                ColumnState(name="name"),
            ]
        )
    assert blocker.signal_triggered


def test_column_state_changed_emitted_on_resize(view_and_model, qtbot) -> None:
    """Direct header resize emits the column_state_changed signal."""
    view, _model = view_and_model
    with qtbot.waitSignal(view.column_state_changed, timeout=1000) as blocker:
        view.header().resizeSection(0, 333)
    assert blocker.signal_triggered
