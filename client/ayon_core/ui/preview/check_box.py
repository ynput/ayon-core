"""checkbox"""

from __future__ import annotations

from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.preview.utils import Style, preview_widget


def build_check_box_preview_widget():
    container = AYContainer(
        layout=AYContainer.Layout.VBox,
        layout_margin=20,
        layout_spacing=20,
    )
    for variant in AYCheckBox.Variants:
        cb1 = AYCheckBox(f"{variant.name} Checkbox", variant=variant)
        container.add_widget(cb1)
    return container


if __name__ == "__main__":
    preview_widget(
        build_check_box_preview_widget,
        style=Style.AYONStyleOverCSS
    )
