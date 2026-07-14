from __future__ import annotations

from qtpy.QtCore import Qt

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.preview.utils import Style, preview_widget


def build_container_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_spacing=10,
        layout_margin=10,
    )
    w.add_widget(
        AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_margin=10,
        )
    )
    w.add_widget(
        AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_margin=10,
        )
    )
    w.add_widget(
        AYContainer(
            layout=AYContainer.Layout.Form,
            variant=AYContainer.Variants.High,
            layout_margin=10,
            layout_spacing=(32, 10),
        )
    )
    last_widget = w._layout.itemAt(2).widget()  # type: ignore
    assert isinstance(last_widget, AYContainer)
    last_widget.set_label_alignment(Qt.AlignRight)
    last_widget.add_row(AYLabel("Label:", dim=True), AYLabel("Value"))
    last_widget.add_row(
        AYLabel("Another Label:", dim=True), AYLabel("Another Value")
    )
    w.setMinimumWidth(200)
    w.setMinimumHeight(400)
    return w


if __name__ == "__main__":
    preview_widget(
        build_container_preview_widget,
        style=Style.AYONStyleOverCSS
    )
