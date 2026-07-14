from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.card_view import AYCardView
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.slider import AYSlider
from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.preview.table_model import (
    HIERARCHICAL_TEST_DATA,
    make_hierarchical_test_fetch,
)
from ayon_core.ui.preview.utils import Style, preview_widget


def _make_card_mapper(
    row_data: dict,
) -> dict:
    status_dict = None
    if row_data.get("status"):
        status_dict = {
            "name": row_data["status"],
            "icon": row_data.get("status__icon", ""),
            "color": row_data.get("status__color", ""),
        }
    return {
        "header": row_data.get("name", ""),
        "title": row_data.get("type", ""),
        "title_icon": row_data.get("name__icon", ""),
        "image_icon": row_data.get("thumb__icon", "image"),
        "status": status_dict,
        "version": row_data.get("version", ""),
    }


def build_card_view_preview_widget() -> QtWidgets.QWidget:
    container = AYContainer(
        variant=AYContainer.Variants.High,
        layout=AYContainer.Layout.VBox,
        layout_margin=20,
        layout_spacing=10,
    )

    top_bar = AYContainer(
        variant=AYContainer.Variants.High,
        layout=AYContainer.Layout.HBox,
        layout_spacing=10,
    )
    label = QtWidgets.QLabel("AYCardView — card width slider + tree mode")
    switch = AYCheckBox(
        "Show Hierarchy", variant=AYCheckBox.Variants.Button
    )

    width_slider = AYSlider(
        label="Card Width",
        variant=AYSlider.Variants.Default,
        value=200,
        minimum=120,
        maximum=300,
        step=10,
    )
    width_slider.setFixedWidth(160)

    top_bar.add_widget(label)
    top_bar.add_widget(width_slider)
    top_bar.add_widget(switch)
    container.add_widget(top_bar)

    columns = [
        TableColumn("name", "Name", width=160, sortable=True),
        TableColumn("status", "Status", width=100, sortable=True),
        TableColumn("type", "Type", width=100, sortable=True),
        TableColumn("version", "Version", width=70, sortable=True),
    ]

    _tree_mode: list[bool] = [False]
    _all_leaf_rows: list[dict] = [
        row
        for rows in HIERARCHICAL_TEST_DATA.values()
        for row in rows
        if not row.get("has_children", False)
    ]
    _hier_fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)

    def _fetch(
        page: int,
        page_size: int,
        sort_key: str | None = None,
        descending: bool = False,
        parent_id: str | None = None,
    ) -> list[dict]:
        if parent_id is not None:
            return _hier_fetch(
                page, page_size, sort_key, descending, parent_id
            )
        if _tree_mode[0]:
            return _hier_fetch(page, page_size, sort_key, descending, None)
        rows = list(_all_leaf_rows)
        if sort_key:
            rows = sorted(
                rows,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page * page_size
        return rows[start : start + page_size]

    model = PaginatedTableModel(
        fetch_page=_fetch,
        columns=columns,
        page_size=50,
    )
    model.set_tree_mode(False)

    card_view = AYCardView(
        variant=AYCardView.Variants.Low,
        card_width=200,
        card_spacing=8,
        card_data_mapper=_make_card_mapper,
    )
    card_view.setModel(model)
    card_view.setMinimumHeight(400)
    container.add_widget(card_view)

    def _on_tree_mode_toggle(enabled: bool) -> None:
        _tree_mode[0] = enabled
        model.set_tree_mode(enabled)

    switch.toggled.connect(_on_tree_mode_toggle)
    width_slider.value_changed.connect(
        lambda v: card_view.set_card_width(v)
    )

    container.setMinimumWidth(800)
    return container


if __name__ == "__main__":
    preview_widget(
        build_card_view_preview_widget,
        style=Style.AYONStyleOverCSS
    )
