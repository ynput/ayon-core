from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.entity_path import AYEntityPath
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.preview.utils import Style, preview_widget


def build_entity_path_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_margin=20,
        layout_spacing=10,
    )
    w.add_widget(AYLabel("AYEntityPath", bold=True, rel_text_size=2))
    w.add_widget(AYEntityPath("project/asset/shot/comp", simple=False))
    w.add_widget(AYEntityPath("project/asset/shot/comp", simple=True))
    return w


if __name__ == "__main__":
    preview_widget(
        build_entity_path_preview_widget,
        style=Style.AYONStyleOverCSS
    )
