"""scroll area"""

from __future__ import annotations

from qtpy.QtCore import Qt, QPoint
from qtpy.QtGui import QPainter, QPaintEvent
from qtpy.QtWidgets import (
    QFrame,
    QScrollArea,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
)

from ..style_types import get_ayon_style
from .style_mixin import StyleMixin


class AYScrollBar(StyleMixin, QScrollBar):
    """AYON styled scroll bar widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QScrollBar.
        **kwargs: Keyword arguments passed to QScrollBar.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())
        self._pressed_subcontrol = QStyle.SubControl.SC_None
        self._active_subcontrols = QStyle.SubControl.SC_None

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
        if self._pressed_subcontrol & QStyle.SubControl.SC_ScrollBarSlider:
            option.activeSubControls = self._pressed_subcontrol
            # State can be used to draw pressed slider in a different way
            option.state |= QStyle.StateFlag.State_Sunken
        else:
            option.activeSubControls = self._active_subcontrols

        get_ayon_style().drawComplexControl(
            QStyle.ComplexControl.CC_ScrollBar, option, p, self
        )

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed_subcontrol = self._active_subcontrols
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._pressed_subcontrol != QStyle.SubControl.SC_None:
            self._pressed_subcontrol = QStyle.SubControl.SC_None
            self.update()

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        self._update_active_subcontrols(event.pos())

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._active_subcontrols != QStyle.SubControl.SC_None:
            self._active_subcontrols = QStyle.SubControl.SC_None
            self.update()

    def _update_active_subcontrols(self, pos: QPoint) -> None:
        style = self.style()
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        active_sub_controls = style.hitTestComplexControl(
            QStyle.ComplexControl.CC_ScrollBar, option, pos, self
        )
        if active_sub_controls != self._active_subcontrols:
            self._active_subcontrols = active_sub_controls
            self.update()


class AYScrollArea(StyleMixin, QScrollArea):
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
