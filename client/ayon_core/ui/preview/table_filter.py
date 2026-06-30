from __future__ import annotations

from dataclasses import dataclass

from qtpy import QtWidgets

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.table_model import (
    TableColumn,
    PaginatedTableModel,
)
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.table_filter import AYTableFilter
from ayon_core.ui.components.tree_model import TreeNode, LazyTreeModel
from ayon_core.ui.components.tree_view import AYTreeView
from ayon_core.ui.preview.utils import Style, preview_widget
from ayon_core.ui.preview.table_model import (
    HIERARCHICAL_TEST_DATA,
    make_hierarchical_test_fetch,
)


@dataclass
class PreviewContext:
    tree_mode: bool = False
    selected_folder: str | None = None


# --- Tree model for folder navigation ---
def _fetch_tree_folders(parent_id: str | None) -> list[TreeNode]:
    rows = HIERARCHICAL_TEST_DATA.get(parent_id, [])
    return [
        TreeNode(
            id=row["id"],
            label=row["name"],
            has_children=True,
            icon="folder",
            icon_color=row.get("name__color", "#f4f5f5"),
        )
        for row in rows
        if row.get("has_children", False)
    ]


def build_table_filter_widget() -> QtWidgets.QWidget:
    """Build test UI: AYTreeView folder navigator + AYTableFilter table."""

    # --- mutable state ---
    context = PreviewContext()

    # All root-level rows (folders + leaves) for tree-mode "show all"
    _all_root_rows: list[dict] = list(HIERARCHICAL_TEST_DATA.get(None, []))

    # All leaf (non-folder) rows across every level for flat "show all"
    _all_leaf_rows: list[dict] = [
        row
        for rows in HIERARCHICAL_TEST_DATA.values()
        for row in rows
        if not row.get("has_children", False)
    ]

    # Wrap the hierarchical fetch so root-level calls respect the
    # currently selected tree folder and current mode.
    _hier_fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)

    def _table_fetch(
        page: int,
        page_size: int,
        sort_key: str | None = None,
        descending: bool = False,
        parent_id: str | None = None,
    ) -> list[dict]:
        if parent_id is not None:
            # tree-mode child expansion — pass through to real data
            return _hier_fetch(
                page, page_size, sort_key, descending, parent_id
            )
        folder_id = context.selected_folder
        if folder_id is None:
            # nothing selected: flat → leaves only; tree → all root rows
            rows = list(
                _all_root_rows if context.tree_mode else _all_leaf_rows
            )
        elif context.tree_mode:
            # folder selected, tree mode: root children of that folder
            rows = list(HIERARCHICAL_TEST_DATA.get(folder_id, []))
        else:
            # folder selected, flat mode: leaf children of that folder
            rows = [
                r
                for r in HIERARCHICAL_TEST_DATA.get(folder_id, [])
                if not r.get("has_children", False)
            ]
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
        return rows[start: start + page_size]

    # --- Table model & filter ---
    columns = [
        TableColumn(
            "thumb", "Thumbnail", width=75, sortable=False, icon="image"
        ),
        TableColumn(
            "name",
            "Name",
            width=250,
            sortable=True,
            icon="label",
            tree_position=True,
        ),
        TableColumn(
            "status", "Status", width=100, sortable=True, icon="circle"
        ),
        TableColumn(
            "type", "Type", width=100, sortable=True, icon="category"
        ),
        TableColumn(
            "author", "Author", width=100, sortable=False, icon="person"
        ),
        TableColumn(
            "version", "Version", width=70, sortable=True, icon="history"
        ),
    ]
    table_model = PaginatedTableModel(
        fetch_page=_table_fetch,
        columns=columns,
        page_size=50,
    )

    filter_bar = AYTableFilter(model=table_model)
    filter_bar.filters_changed.connect(
        lambda criteria: print(
            "[test]  filters changed: "
            f"{[(c.key, c.values) for c in criteria]}"
        )
    )

    switch = AYCheckBox(
        "Show Hierarchy", variant=AYCheckBox.Variants.Button
    )

    def _on_tree_mode_toggle(enabled: bool) -> None:
        context.tree_mode = enabled
        table_model.set_tree_mode(enabled)

    switch.toggled.connect(_on_tree_mode_toggle)

    folder_tree_model = LazyTreeModel(fetch_children=_fetch_tree_folders)
    tree_view = AYTreeView(variant=AYTreeView.Variants.Low)
    tree_view.setModel(folder_tree_model)
    tree_view.setFixedWidth(180)

    def _on_tree_selection(selected, deselected) -> None:
        indexes = selected.indexes()
        if indexes:
            node = indexes[0].internalPointer()
            folder_id = node.tree_node.id if node.tree_node else None
            context.selected_folder = folder_id
            print(f"[test]  folder selected: {folder_id!r}")
        else:
            context.selected_folder = None
            print("[test]  no folder selected (showing all leaf rows)")
        table_model.reset_data()

    tree_view.selection_changed.connect(_on_tree_selection)

    # --- Layout ---
    outer = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        layout_margin=10,
        layout_spacing=8,
    )

    right = AYContainer(
        layout=AYContainer.Layout.VBox,
        layout_margin=0,
        layout_spacing=4,
    )

    filter_row = AYContainer(
        layout=AYContainer.Layout.HBox,
        layout_margin=0,
        layout_spacing=4,
    )
    filter_row.add_widget(filter_bar, stretch=1)
    filter_row.add_widget(switch)
    right.add_widget(filter_row)

    table = AYTableView()
    table.setModel(filter_bar.filter_model)
    table.setMinimumHeight(400)
    table.selection_changed.connect(
        lambda sel, desel: print(
            f"[test]  table selection: {[i.data() for i in sel.indexes()]}"
        )
    )
    right.add_widget(table, stretch=1)

    outer.add_widget(tree_view)
    outer.add_widget(right, stretch=1)
    outer.setMinimumWidth(900)
    return outer


if __name__ == "__main__":
    preview_widget(
        build_table_filter_widget,
        style=Style.AYONStyleOverCSS
    )
