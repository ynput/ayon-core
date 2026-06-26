from __future__ import annotations

import os

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.page_button import AYPageButton
from ayon_core.ui.preview.utils import Style, preview_widget


def build_page_button_widget():
    container = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.High,
        layout_spacing=2,
        layout_margin=12,
    )

    rows = [
        # (label, value, icon)
        ("Featured version", "Done", "star"),
        ("Settings", "", "settings"),
        (
            (
                "A very long label that should be elided when the window "
                "is narrow"
            ),
            "Value",
            "info",
        ),
        ("No icon, with value", "Some text", None),
        ("No value, no icon", "", None),
    ]

    for label, value, icon in rows:
        btn = AYPageButton(
            label=label,
            value=value,
            icon=icon,
            tooltip=f"{label!r} button",
        )
        container.add_widget(btn)

    # Disabled example
    disabled_btn = AYPageButton(
        label="Disabled entry",
        value="N/A",
        icon="block",
    )
    disabled_btn.setEnabled(False)
    container.add_widget(disabled_btn)

    container.addStretch(1)
    return container


if __name__ == "__main__":
    os.environ["QT_SCALE_FACTOR"] = "1"
    preview_widget(
        build_page_button_widget,
        style=Style.AYONStyleOverCSS
    )
