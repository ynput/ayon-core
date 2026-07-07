from __future__ import annotations

from typing import Callable

from qtpy import QtWidgets
from qtpy.QtWidgets import QWidget
from qtpy.QtCore import QModelIndex

from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.preview.utils import Style, preview_widget
from ayon_core.ui.preview.table_model import (
    HIERARCHICAL_TEST_DATA,
    make_hierarchical_test_fetch,
)


def _make_button_factory(
    label: str,
) -> Callable[[QModelIndex, QWidget], QWidget]:
    """Create a widget factory that returns a small button.

    Args:
        label: Button text.

    Returns:
        A callable suitable for ``TableColumn.widget_factory``.
    """

    def _factory(index: QModelIndex, parent: QWidget) -> QWidget:
        btn = AYButton(
            label,
            variant=AYButton.Variants.Text,
            parent=parent,
        )
        btn.setFixedHeight(28)
        btn.clicked.connect(
            lambda: print(f"Button clicked: row={index.row()}")
        )
        return btn

    return _factory


def build_table_view_preview_widget() -> QtWidgets.QWidget:
    """Build test UI with one AYTableView per variant."""

    container = AYContainer(
        variant=AYContainer.Variants.High,
        layout=AYContainer.Layout.VBox,
        layout_margin=20,
        layout_spacing=10,
    )

    # label + hierarchy switch
    top_bar = AYContainer(
        variant=AYContainer.Variants.High,
        layout=AYContainer.Layout.HBox,
    )
    label = QtWidgets.QLabel("variant: tree mode (hierarchical)")
    switch = AYCheckBox(
        "Show Hierarchy", variant=AYCheckBox.Variants.Button
    )
    top_bar.add_widget(label)
    top_bar.add_widget(switch)
    container.add_widget(top_bar)

    # define model — "actions" column uses a widget factory
    tree_columns = [
        TableColumn("thumb", "Thumbnail", width=75, sortable=False),
        TableColumn(
            "name", "Name", width=160, sortable=True, tree_position=True
        ),
        TableColumn("status", "Status", width=100, sortable=True),
        TableColumn("type", "Type", width=100, sortable=True),
        TableColumn("author", "Author", width=100, sortable=False),
        TableColumn("version", "Version", width=70, sortable=True),
        TableColumn(
            "actions",
            "Actions",
            width=90,
            sortable=False,
            widget_factory=_make_button_factory("Open"),
        ),
    ]
    tree_fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)
    tree_model = PaginatedTableModel(
        fetch_page=tree_fetch,
        columns=tree_columns,
        page_size=50,
    )
    tree_model.set_tree_mode(False)

    # define view
    tree_view = AYTableView(variant=AYTableView.Variants.Low)
    tree_view.setModel(tree_model)
    tree_view.setMinimumHeight(280)
    container.add_widget(tree_view)
    switch.toggled.connect(tree_model.set_tree_mode)

    tree_view.selection_changed.connect(
        lambda selected, deselected, tv=tree_view: print(
            "selection changed: "
            f"Selected {[i.data() for i in selected.indexes()]} "
            f"and deselected {[i.data() for i in deselected.indexes()]}) "
            f"(full selection: {[i.data() for i in tv.selectedIndexes()]})"
        )
    )

    container.setMinimumWidth(700)
    return container


if __name__ == "__main__":
    preview_widget(
        build_table_view_preview_widget,
        style=Style.AYONStyleOverCSS
    )
