from __future__ import annotations

from qtpy.QtWidgets import QWidget

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.slider import AYSlider
from ayon_core.ui.preview.utils import Style, preview_widget


def build_slider_widget() -> QWidget:
    container = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.High,
        layout_margin=20,
        layout_spacing=10,
    )
    container.setMinimumWidth(400)

    for variant in AYSlider.Variants:
        row = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants(variant.value),
            layout_margin=20,
            layout_spacing=10,
        )

        s1 = AYSlider(
            label="Grid size",
            value=220,
            minimum=0,
            maximum=500,
            step=1,
            variant=variant,
        )
        row.add_widget(s1)

        s2 = AYSlider(
            label="Opacity (disabled)",
            value=25,
            minimum=0,
            maximum=100,
            variant=variant,
        )
        s2.setEnabled(False)
        row.add_widget(s2)

        s3 = AYSlider(
            label="Step 10",
            value=30,
            minimum=0,
            maximum=100,
            step=10,
            variant=variant,
        )
        row.add_widget(s3)

        container.add_widget(row)

    return container


if __name__ == "__main__":
    preview_widget(
        build_slider_widget,
        style=Style.AYONStyleOverCSS
    )
