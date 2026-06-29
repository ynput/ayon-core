from __future__ import annotations

from qtpy.QtWidgets import QWidget

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.line_edit import AYLineEdit, QLineEditVariants
from ayon_core.ui.preview.utils import Style, preview_widget


def build_line_edit_widget() -> QWidget:
    container = AYContainer(
        variant=AYContainer.Variants.Low,
        layout=AYContainer.Layout.HBox,
        layout_margin=20,
        layout_spacing=20,
    )
    container.setMinimumWidth(300)

    disabled_edit = AYLineEdit(
        placeholder="Disabled",
    )
    disabled_edit.setEnabled(False)
    container.add_widget(disabled_edit)

    for variant in QLineEditVariants:
        line_edit = AYLineEdit(
            placeholder="Enter text here",
            variant=variant,
        )
        container.add_widget(line_edit)

    return container


if __name__ == "__main__":
    preview_widget(
        build_line_edit_widget,
        style=Style.AYONStyleOverCSS
    )
