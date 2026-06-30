from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.layouts import AYVBoxLayout
from ayon_core.ui.components.tree_model import (
    LazyTreeModel,
    TreeNode,
)
from ayon_core.ui.components.tree_view import AYTreeView
from ayon_core.ui.preview.utils import Style, preview_widget


PRODUCTS_TEST_DATA: dict[str | None, list[TreeNode]] = {
    None: [
        TreeNode("assets", "Assets", has_children=True, icon="category"),
        TreeNode("shots", "Shots", has_children=True, icon="theaters"),
        TreeNode("refs", "References", has_children=False, icon="menu_book"),
    ],
    "assets": [
        TreeNode("char", "Characters", has_children=True, icon="folder"),
        TreeNode("props", "Props", has_children=True, icon="folder"),
    ],
    "char": [
        TreeNode("char_pi", "pigeon", icon="smart_toy"),
        TreeNode("char_ro", "robot", icon="smart_toy"),
    ],
    "props": [
        TreeNode("props_p", "Peace", icon="self_improvement"),
        TreeNode("props_l", "Love", icon="favorite"),
    ],
    "shots": [
        TreeNode("sh010", "SH010", has_children=True, icon="folder"),
        TreeNode("sh020", "SH020", has_children=True, icon="folder"),
        TreeNode("sh030", "SH030", has_children=True, icon="folder"),
    ],
    "sh010": [
        TreeNode("sh010_anim", "Animation", icon="directions_run"),
        TreeNode("sh010_lgt", "Lighting", icon="highlight"),
    ],
    "sh020": [
        TreeNode("sh020_anim", "Animation", icon="directions_run"),
        TreeNode("sh020_comp", "Compositing", icon="layers"),
    ],
    "sh030": [
        TreeNode("sh030_fx", "FX", icon="fireplace"),
        TreeNode("sh030_lgt", "Lighting", icon="highlight"),
    ],
}


REVIEWS_TEST_DATA: dict[str | None, list[TreeNode]] = {
    None: [
        TreeNode("rev1", "Review 1", has_children=False, icon="subscriptions"),
        TreeNode("rev2", "Review 2", has_children=False, icon="subscriptions"),
        TreeNode("rev3", "Review 3", has_children=False, icon="subscriptions"),
    ]
}


def fetch_children(
    parent_id: str | None,
) -> list[TreeNode]:
    print(f"fetching children of {parent_id}")
    return PRODUCTS_TEST_DATA.get(parent_id, [])


def build_tree_view_preview_widget() -> QtWidgets.QWidget:
    """Show one AYTreeView per variant with lazy-loaded fake data."""
    container = QtWidgets.QWidget()
    root_lyt = AYVBoxLayout(container, margin=8, spacing=8)

    for variant in AYTreeView.Variants:
        label = QtWidgets.QLabel(f"variant: {variant.value}")
        label.setFixedHeight(20)
        root_lyt.addWidget(label)

        tv = AYTreeView(variant=variant)
        tv.setModel(LazyTreeModel(fetch_children=fetch_children))
        tv.setMinimumHeight(160)
        root_lyt.addWidget(tv)

        tv.selection_changed.connect(
            lambda selected, deselected, tv=tv: print(
                "selection changed: "
                f"Selected {[i.data() for i in selected.indexes()]} "
                "and deselected "
                f"{[i.data() for i in deselected.indexes()]}) "
                "(full selection: "
                f"{[i.data() for i in tv.selectedIndexes()]})"
            )
        )

    container.setMinimumWidth(360)
    return container


if __name__ == "__main__":
    preview_widget(
        build_tree_view_preview_widget,
        style=Style.AYONStyleOverCSS
    )
