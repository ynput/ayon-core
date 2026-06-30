from __future__ import annotations

from functools import partial

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.slicer import TreeFilterProxyModel, AYSlicer
from ayon_core.ui.components.tree_model import TreeNode, LazyTreeModel
from ayon_core.ui.components.tree_view import AYTreeView
from ayon_core.ui.preview.utils import Style, preview_widget
from ayon_core.ui.preview.tree_view import (
    PRODUCTS_TEST_DATA,
    REVIEWS_TEST_DATA,
)

_DATA = PRODUCTS_TEST_DATA


def fetch_children(parent_id: str | None,) -> list[TreeNode]:
    print(f"fetching children of {parent_id!r}")
    return _DATA.get(parent_id, [])


def _update_model(tv, _slicer, _category: str):
    global _DATA
    print(f"category changed to {_category!r}")
    if _category == "Products":
        _DATA = PRODUCTS_TEST_DATA
    elif _category == "Reviews":
        _DATA = REVIEWS_TEST_DATA
    # reset the model
    mod = tv.model()
    if isinstance(mod, TreeFilterProxyModel):
        mod = mod.sourceModel()
    mod.reset()
    _slicer.set_model(mod, view=tv)


def build_slicer_widget():
    w = AYContainer(
        variant=AYContainer.Variants.High,
        layout=AYContainer.Layout.VBox,
        layout_margin=20,
        layout_spacing=10,
    )
    w.setMinimumWidth(400)

    items = [
        {
            "text": "Products",
            "short_text": "PRD",
            "icon": "photo_library",
            "color": "#f4f5f5",
        },
        {
            "text": "Reviews",
            "short_text": "REV",
            "icon": "subscriptions",
            "color": "#f4f5f5",
        },
    ]

    slicer = AYSlicer(item_list=items)
    w.add_widget(slicer)

    tv = AYTreeView(variant=AYTreeView.Variants.Low)
    tv.setModel(LazyTreeModel(fetch_children=fetch_children))
    tv.setMinimumHeight(300)
    w.add_widget(tv)

    # pass the data to be filtered.
    slicer.set_model(tv.model(), view=tv)

    # update the model when the slicer changes
    slicer.category_changed.connect(partial(_update_model, tv, slicer))

    return w


if __name__ == "__main__":
    preview_widget(
        build_slicer_widget,
        Style.AYONStyleOverCSS
    )
