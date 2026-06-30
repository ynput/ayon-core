from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.frame import AYFrame
from ayon_core.ui.components.layouts import AYVBoxLayout
from ayon_core.ui.preview.utils import Style, preview_widget


def build_frame_preview_widget():
    """All frame variants."""
    w = QtWidgets.QWidget()
    w.setMinimumWidth(300)
    lyt = AYVBoxLayout(w, margin=8, spacing=8)

    for variant in AYFrame.Variants:
        frame = AYFrame(variant=variant)
        frame.setFixedHeight(40)
        frame.setToolTip(variant.value)
        lyt.addWidget(frame)

    return w


if __name__ == "__main__":
    preview_widget(
        build_frame_preview_widget,
        style=Style.AYONStyleOverCSS
    )
