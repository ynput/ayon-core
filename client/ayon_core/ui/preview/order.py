from __future__ import annotations

from qtpy.QtWidgets import QWidget

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.order import AYOrder
from ayon_core.ui.preview.utils import Style, preview_widget


def build_order_widget() -> QWidget:
    root = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_margin=20,
        layout_spacing=20,
    )
    root.setMinimumWidth(400)

    def _on_order(new_order: list[str]) -> None:
        print("order_changed:", new_order)

    # Default variant – drag_indicator icons
    order_default = AYOrder(
        options=["Alpha", "Beta", "Gamma", "Delta"],
        variant=AYOrder.Variant.Low,
    )
    order_default.order_changed.connect(_on_order)
    root.add_widget(order_default)

    # High variant – custom icons
    order_high = AYOrder(
        options=["Compositing", "Lighting", "Rigging", "Modeling"],
        icons=["layers", "light_mode", "account_tree", "deployed_code"],
        variant=AYOrder.Variant.High,
    )
    order_high.order_changed.connect(_on_order)
    root.add_widget(order_high)

    return root


if __name__ == "__main__":
    preview_widget(
        build_order_widget,
        style=Style.AYONStyleOverCSS
    )
