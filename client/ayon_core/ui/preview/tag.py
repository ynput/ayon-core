from __future__ import annotations

from qtpy import QtWidgets, QtGui

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.tag import AYTag
from ayon_core.ui.preview.utils import Style, preview_widget


def _connect_signals(w: QtWidgets.QWidget):
    w.tag_removed.connect(lambda x: print(f"Tag removed: {x!r}"))
    w.tag_expanded.connect(lambda x: print(f"Tag expanded: {x!r}"))


def build_tag_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.HBox,
        variant=AYContainer.Variants.Low,
        layout_margin=10,
        layout_spacing=4,
    )
    wlyt = w.layout()
    if wlyt:
        wlyt.setSizeConstraint(
            QtWidgets.QLayout.SizeConstraint.SetFixedSize,
        )

    w.add_widget(AYTag("red", QtGui.QColor("#ff4444")))
    w.add_widget(AYTag("green", QtGui.QColor("#44ff44")))
    w.add_widget(AYTag("blue", QtGui.QColor("#4444ff")))
    w.add_widget(AYTag("red_desat", QtGui.QColor("#ff9999")))
    w.add_widget(AYTag("green_desat", QtGui.QColor("#99ff99")))
    w.add_widget(
        AYTag(
            "blue_desat", QtGui.QColor("#9999ff"), label="Desaturated Blue"
        )
    )
    w.add_widget(AYTag("redDark", QtGui.QColor("#553333")))
    w.add_widget(AYTag("greenDark", QtGui.QColor("#335533")))
    w.add_widget(
        AYTag("blueDark", QtGui.QColor("#333355"), label="Dark Blue")
    )

    for child in w.children():
        if isinstance(child, AYTag):
            _connect_signals(child)

    return w


if __name__ == "__main__":
    preview_widget(
        build_tag_preview_widget,
        style=Style.AYONStyleOverCSS
    )
