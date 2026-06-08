from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from ..color_utils import compute_color_for_contrast
from ..style_types import get_ayon_style
from ..variants import QFrameVariants
from .buttons import AYButton
from .frame import AYFrame
from .label import AYLabel


class AYTag(AYFrame):
    """A widget used to display a tag as a pill with a color and text,
    a delete and an expand button."""

    tag_removed = QtCore.Signal(str)
    tag_expanded = QtCore.Signal(str)

    def __init__(
        self,
        name: str,
        color: QtGui.QColor,
        label: str | None = None,
        parent=None,
    ):
        super().__init__(parent, variant=QFrameVariants.Tag, margin=0)
        self._tag_name = name
        self._tag_label = label
        self._bg_color = color
        self._fg_color = None
        self.setStyle(get_ayon_style())
        self.init_ui()

    @property
    def background_color(self) -> QtGui.QColor:
        return self._bg_color

    @property
    def foreground_color(self) -> QtGui.QColor:
        if self._fg_color is None:
            self._fg_color = compute_color_for_contrast(
                self._bg_color.toTuple(),
                (0, 0, 0, 255),
            )
        return self._fg_color

    def init_ui(self):
        self.lyt = QtWidgets.QHBoxLayout(self)
        self.lyt.setContentsMargins(2, 2, 2, 2)
        self.lyt.setSpacing(4)
        self.lyt.setSizeConstraint(
            QtWidgets.QLayout.SizeConstraint.SetMinimumSize
        )

        self.delete_button = AYButton(
            icon="close",
            icon_color=self.foreground_color.name(),
            icon_size=16,
            variant=AYButton.Variants.Tag,
            contrast_color=self.background_color,
            tooltip=f"Remove tag {self._tag_name!r}",
        )

        self.label = AYLabel(
            self._tag_label or self._tag_name,
            variant=AYLabel.Variants.Tag,
            text_color=self.foreground_color.name(),
            contrast_color=self.background_color,
        )
        self.label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

        self.expand_button = AYButton(
            icon="arrow_drop_down",
            icon_color=self.foreground_color.name(),
            icon_size=16,
            variant=AYButton.Variants.Tag,
            contrast_color=self.background_color,
            tooltip=f"Expand tag {self._tag_name!r}",
        )

        self.lyt.addWidget(self.delete_button)
        self.lyt.addWidget(self.label)
        self.lyt.addWidget(self.expand_button)

        self.delete_button.clicked.connect(self._delete_tag)
        self.expand_button.clicked.connect(self._expand_tag)

    def _delete_tag(self):
        self.tag_removed.emit(self._tag_name)

    def _expand_tag(self):
        self.tag_expanded.emit(self._tag_name)


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def _connect_signals(w: QtWidgets.QWidget):
        w.tag_removed.connect(lambda x: print(f"Tag removed: {x!r}"))
        w.tag_expanded.connect(lambda x: print(f"Tag expanded: {x!r}"))

    def _build():
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

    test(_build, style=Style.AyonStyleOverCSS)
