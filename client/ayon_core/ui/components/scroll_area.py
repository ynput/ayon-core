"""scroll area"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QPainter, QPaintEvent
from qtpy.QtWidgets import (
    QFrame,
    QScrollArea,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
)

from ..style import get_ayon_style


class AYScrollBar(QScrollBar):
    """AYON styled scroll bar widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QTextEdit.
        **kwargs: Keyword arguments passed to QTextEdit.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())

    def initStyleOption(self, option: QStyleOptionSlider) -> None:
        super().initStyleOption(option)
        SC = QStyle.SubControl
        option.subControls = (
            SC.SC_None
            | SC.SC_ScrollBarAddPage
            | SC.SC_ScrollBarSubPage
            | SC.SC_ScrollBarSlider
        )

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        p = QPainter(self)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        get_ayon_style().drawComplexControl(
            QStyle.ComplexControl.CC_ScrollBar, option, p, self
        )
        return


class AYScrollArea(QScrollArea):
    """AYON styled scroll area widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QTextEdit.
        **kwargs: Keyword arguments passed to QTextEdit.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())
        # AYONStyle's FrameDrawer would otherwise draw a 1px frame around the
        # viewport, which shows as a thin line on the right edge (above the
        # scrollbar) and along the bottom.
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.setVerticalScrollBar(AYScrollBar(Qt.Orientation.Vertical))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBar(AYScrollBar(Qt.Orientation.Horizontal))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
