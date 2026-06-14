from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from ..style_types import get_ayon_style
from ..utils import color_blend
from ..variants import QFrameVariants
from .style_mixin import StyleMixin


class AYFrame(StyleMixin, QtWidgets.QFrame):
    Variants = QFrameVariants

    def __init__(
        self,
        *args,
        bg=False,
        variant: Variants = Variants.Default,
        margin=0,
        bg_tint="",
        **kwargs,
    ):
        # Convert enum to string if needed
        self._bg: bool = bg
        self._variant_str = variant.value
        self._bg_tint = bg_tint
        self._bg_color = None

        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())

        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.setContentsMargins(margin, margin, margin, margin)

    def paintEvent(self, arg__1: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        option = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(option)
        # print(f"opt: {option}")
        get_ayon_style().drawControl(
            QtWidgets.QStyle.ControlElement.CE_ShapedFrame, option, p, self
        )

    def get_bg_color(self, base_color: str):
        if not self._bg_color:
            if self._bg_tint:
                self._bg_color = color_blend(base_color, self._bg_tint, 0.1)
            else:
                return base_color
        return self._bg_color


if __name__ == "__main__":
    from ..tester import Style, test
    from .layouts import AYVBoxLayout

    def _build():
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

    test(_build, style=Style.AyonStyleOverCSS)
