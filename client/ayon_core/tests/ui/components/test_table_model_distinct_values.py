"""Distinct values offered by the table model to the filter picker."""

from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)


def _model(rows: list[dict]) -> PaginatedTableModel:
    def _fetch_page(_page, _page_size, _sort_key, _descending, parent_id):
        return rows if parent_id is None else []

    model = PaginatedTableModel(
        fetch_page=_fetch_page,
        columns=[TableColumn(key="value", label="Value")],
        no_async=True,
    )
    model.reset_data()
    if model.canFetchMore():
        model.fetchMore()
    assert model.rowCount() == len(rows)
    return model


def test_list_values_contribute_their_items(qapp):
    model = _model([
        {"id": "1", "value": ["render", "review"]},
        {"id": "2", "value": ["review", "  "]},
        {"id": "3", "value": []},
        {"id": "4", "value": None},
    ])

    assert model.get_distinct_values("value") == ["render", "review"]


def test_scalar_values_are_kept_whole(qapp):
    model = _model([
        {"id": "1", "value": "render, review"},
        {"id": "2", "value": 25},
        {"id": "3", "value": ""},
    ])

    assert model.get_distinct_values("value") == ["25", "render, review"]
