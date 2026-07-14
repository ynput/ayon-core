from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.filter import AYFilterByCategory, FilterItem
from ayon_core.ui.preview.utils import Style, preview_widget


def build_filter_preview_widget() -> QtWidgets.QWidget:
    """Build test widget."""
    w = AYContainer(variant=AYContainer.Variants.High, layout_margin=10)
    w.add_widget(
        AYFilterByCategory(
            label="Sort by",
            items=[
                FilterItem("task", "Task"),
                FilterItem("folder", "Folder", selected=True),
                FilterItem("status", "Status", selected=True),
                FilterItem("priority", "Priority"),
                FilterItem("due_date", "Due Date"),
            ],
        )
    )
    w.addStretch(10)
    return w


if __name__ == "__main__":
    preview_widget(
        build_filter_preview_widget,
        style=Style.AYONStyleOverCSS
    )
