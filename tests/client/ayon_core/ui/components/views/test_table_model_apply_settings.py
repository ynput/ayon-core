"""Tests for PaginatedTableModel.apply_settings/capture_settings."""

from __future__ import annotations

from typing import Any

from qtpy.QtCore import Qt

from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.components.views.data_models import (
    ColumnState,
    ViewSettings,
)


_ROWS: list[dict[str, Any]] = [
    {"id": f"r{i}", "name": f"Row {i}", "status": "ok", "version": f"v{i}"}
    for i in range(5)
]


def _make_fetch():
    """Return a flat fetch callable yielding the static row list."""

    def _fetch(page, page_size, sort_key, descending, parent_id):  # noqa: ANN001,ARG001,E501
        if page != 0:
            return []
        return list(_ROWS)

    return _fetch


def _make_model() -> PaginatedTableModel:
    """Build a no_async PaginatedTableModel with three columns."""
    cols = [
        TableColumn("name", "Name", width=100),
        TableColumn("status", "Status", width=80),
        TableColumn("version", "Version", width=60),
    ]
    return PaginatedTableModel(
        fetch_page=_make_fetch(),
        columns=cols,
        page_size=10,
        no_async=True,
    )


def test_apply_settings_reorders_columns() -> None:
    """apply_settings reorders the model's columns by ``name`` key."""
    model = _make_model()
    settings = ViewSettings(
        columns=[
            ColumnState(name="version"),
            ColumnState(name="name"),
            ColumnState(name="status"),
        ]
    )
    model.apply_settings(settings)
    assert [c.key for c in model.columns] == ["version", "name", "status"]


def test_apply_settings_resizes_columns() -> None:
    """A non-None ``width`` overrides the TableColumn width."""
    model = _make_model()
    settings = ViewSettings(
        columns=[
            ColumnState(name="name", width=222),
            ColumnState(name="status"),
            ColumnState(name="version"),
        ]
    )
    model.apply_settings(settings)
    by_key = {c.key: c for c in model.columns}
    assert by_key["name"].width == 222
    assert by_key["status"].width == 80
    assert by_key["version"].width == 60


def test_apply_settings_sets_sort() -> None:
    """sort_by/sort_desc are translated to the model's sort state."""
    model = _make_model()
    settings = ViewSettings(
        columns=[ColumnState(name=k) for k in ("name", "status", "version")],
        sort_by="status",
        sort_desc=True,
    )
    model.apply_settings(settings)
    assert model.columns[model._sort_column].key == "status"
    assert model._sort_order == Qt.SortOrder.DescendingOrder


def test_apply_settings_unknown_sort_key_becomes_unsorted() -> None:
    """An unknown sort_by key results in no active sort column."""
    model = _make_model()
    settings = ViewSettings(
        columns=[ColumnState(name=k) for k in ("name", "status", "version")],
        sort_by="does_not_exist",
    )
    model.apply_settings(settings)
    assert model._sort_column == -1


def test_apply_settings_unknown_columns_are_preserved_on_capture() -> None:
    """Unknown column keys are dropped from the model but re-emitted."""
    model = _make_model()
    settings = ViewSettings(
        columns=[
            ColumnState(name="version"),
            ColumnState(name="__row_selection__", pinned=True),
            ColumnState(name="thumbnail", width=80),
            ColumnState(name="name"),
        ]
    )
    model.apply_settings(settings)
    # Unknown columns are not in the model itself.
    assert [c.key for c in model.columns] == ["version", "name", "status"]
    # But they come back in capture_settings, in the original order.
    captured = model.capture_settings()
    names = [c.name for c in captured.columns]
    assert "__row_selection__" in names
    assert "thumbnail" in names


def test_apply_settings_keeps_columns_missing_from_state() -> None:
    """Catalog columns not mentioned in settings are appended at the end."""
    model = _make_model()
    settings = ViewSettings(columns=[ColumnState(name="version")])
    model.apply_settings(settings)
    assert [c.key for c in model.columns] == ["version", "name", "status"]


def test_capture_settings_sort_roundtrip() -> None:
    """capture_settings reflects the current sort_by/sort_desc."""
    model = _make_model()
    settings_in = ViewSettings(
        columns=[ColumnState(name=k) for k in ("name", "status", "version")],
        sort_by="status",
        sort_desc=True,
    )
    model.apply_settings(settings_in)
    captured = model.capture_settings()
    assert captured.sort_by == "status"
    assert captured.sort_desc is True


def test_capture_settings_no_sort_returns_none() -> None:
    """When no sort is active, capture_settings.sort_by is None."""
    model = _make_model()
    captured = model.capture_settings()
    assert captured.sort_by is None
    assert captured.sort_desc is False


def test_apply_settings_width_zero_means_auto() -> None:
    """A width of 0 in ColumnState maps to auto (TableColumn.width=0)."""
    model = _make_model()
    settings = ViewSettings(
        columns=[
            ColumnState(name="name", width=0),
            ColumnState(name="status"),
            ColumnState(name="version"),
        ]
    )
    model.apply_settings(settings)
    by_key = {c.key: c for c in model.columns}
    assert by_key["name"].width == 0


def test_apply_settings_rejects_non_view_settings() -> None:
    """apply_settings raises TypeError for non-ViewSettings arguments."""
    model = _make_model()
    import pytest

    with pytest.raises(TypeError):
        model.apply_settings({"columns": []})  # type: ignore[arg-type]
