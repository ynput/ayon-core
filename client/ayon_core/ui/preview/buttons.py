from __future__ import annotations

import os

from qtpy import QtWidgets

from ayon_core.ui.variants import QPushButtonVariants
from ayon_core.ui.components.buttons import AYButton, AYButtonMenu
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.preview.utils import Style, preview_widget


def build_buttons_preview_widget():
    # Create and show the test widget
    widget = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.High,
        layout_spacing=10,
        layout_margin=10,
    )

    variants = [v for v in QPushButtonVariants]

    l1 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        parent=widget,
        layout_spacing=10,
        layout_margin=10,
    )
    for var in variants:
        b = AYButton(
            f"{var.value} button",
            variant=var,
            tooltip=f"{var.value}",
        )
        l1.add_widget(b)

    l2 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        parent=widget,
        layout_spacing=10,
        layout_margin=10,
    )
    for var in variants:
        b = AYButton(
            f"{var.value} button",
            variant=var,
            icon="add",
            tooltip=f"{var.value}",
        )
        l2.add_widget(b)

    l3 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        parent=widget,
        layout_spacing=10,
        layout_margin=10,
    )
    for var in variants:
        b = AYButton(
            variant=var,
            icon="home",
            tooltip=f"{var.value}",
        )
        l3.add_widget(b)
    l3.addStretch(1)

    l4 = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        parent=widget,
        layout_spacing=10,
        layout_margin=10,
    )

    def populate_menu(container: QtWidgets.QFrame) -> None:
        layout = container.layout()
        assert layout is not None
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        for i in range(5):
            btn = AYButton(
                f"Option {i + 1}",
                parent=container,
                variant=AYButton.Variants.Text,
                icon=f"counter_{i + 1}",
                checkable=True,
            )
            layout.addWidget(btn)

    menu_btn = AYButtonMenu(
        "Menu Button",
        variant=QPushButtonVariants.Filled,
        icon="layers",
        populate_callback=populate_menu,
    )
    l4.add_widget(menu_btn)
    l4.addStretch(1)

    widget.add_widget(l1)
    widget.add_widget(l2)
    widget.add_widget(l3)
    widget.add_widget(l4)

    return widget


if __name__ == "__main__":
    os.environ["QT_SCALE_FACTOR"] = "1"
    preview_widget(
        build_buttons_preview_widget, style=Style.AYONStyleOverCSS
    )
