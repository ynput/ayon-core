"""scroll area"""

from __future__ import annotations

from qtpy.QtCore import Qt, QPoint, QSize
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

    Mouse interaction is handled here too, instead of by QScrollBar. When
    any ancestor (or the app) has a stylesheet, Qt wraps ``self.style()``
    in a ``QStyleSheetStyle`` which, as soon as a rule like
    ``QWidget { background: ... }`` matches, computes its own scrollbar
    geometry (including arrow buttons). QScrollBar's C++ mouse handling
    would then hit-test against that geometry rather than what we paint.
    Using the raw AYONStyle for both keeps them in sync.

    Args:
        *args: Positional arguments passed to QScrollBar.
        **kwargs: Keyword arguments passed to QScrollBar.
    """

    # Delays (ms) before and between repeated page steps while pressed.
    _repeat_threshold = 500
    _repeat_time = 50

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())
        self._pressed_subcontrol = QStyle.SubControl.SC_None
        self._active_subcontrols = QStyle.SubControl.SC_None
        # Offset of the press position from the slider start while dragging
        self._click_offset = 0
        # Last mouse position while a page area is pressed
        self._page_press_pos: QPoint | None = None

    def initStyleOption(self, option: QStyleOptionSlider) -> None:
        super().initStyleOption(option)
        SC = QStyle.SubControl
        option.subControls = (
            SC.SC_None
            | SC.SC_ScrollBarAddPage
            | SC.SC_ScrollBarSubPage
            | SC.SC_ScrollBarSlider
        )

    def sizeHint(self) -> QSize:
        # Same as QScrollBar.sizeHint but with the raw AYONStyle, so a host
        # stylesheet (e.g. 'QScrollBar:vertical { width: 15px; }') cannot
        # change the space reserved for the scrollbar.
        self.ensurePolished()
        style = get_ayon_style()
        option = self._style_option()
        extent = style.pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent, option, self
        )
        slider_min = style.pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarSliderMin, option, self
        )
        if self.orientation() == Qt.Orientation.Horizontal:
            size = QSize(extent * 2 + slider_min, extent)
        else:
            size = QSize(extent, extent * 2 + slider_min)
        return style.sizeFromContents(
            QStyle.ContentsType.CT_ScrollBar, option, size, self
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
        SC = QStyle.SubControl
        button = event.button()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        # Middle click and shift + left click jump the slider to the cursor
        jump = button == Qt.MouseButton.MiddleButton or (
            button == Qt.MouseButton.LeftButton and shift
        )
        if (
            (button != Qt.MouseButton.LeftButton and not jump)
            or self._pressed_subcontrol != SC.SC_None
            or self.maximum() == self.minimum()
        ):
            event.ignore()
            return

        event.accept()
        pos = event.pos()
        sc = self._hit_test(pos)
        if sc == SC.SC_None:
            return

        if jump:
            # Center the slider under the cursor, then drag from there
            _start, length = self._slider_span()
            self._click_offset = length // 2
            self.setSliderDown(True)
            self.setSliderPosition(self._pixel_to_value(pos))
            sc = SC.SC_ScrollBarSlider
        elif sc == SC.SC_ScrollBarSlider:
            start, _length = self._slider_span()
            self._click_offset = self._pos_along(pos) - start
            self.setSliderDown(True)
        else:
            action = (
                QScrollBar.SliderAction.SliderPageStepSub
                if sc == SC.SC_ScrollBarSubPage
                else QScrollBar.SliderAction.SliderPageStepAdd
            )
            self._page_press_pos = pos
            self.triggerAction(action)
            self.setRepeatAction(
                action, self._repeat_threshold, self._repeat_time
            )

        self._pressed_subcontrol = sc
        self._active_subcontrols = sc
        self.update()

    def mouseMoveEvent(self, event) -> None:
        SC = QStyle.SubControl
        pos = event.pos()
        if self._pressed_subcontrol == SC.SC_ScrollBarSlider:
            self.setSliderPosition(self._pixel_to_value(pos))
            return

        if self._page_press_pos is not None:
            self._page_press_pos = pos
            # Pause repeating while outside the pressed page area and resume
            # when coming back, like QScrollBar does.
            inside = self._hit_test(pos) == self._pressed_subcontrol
            if not inside:
                self.setRepeatAction(QScrollBar.SliderAction.SliderNoAction)
            elif self.repeatAction() == QScrollBar.SliderAction.SliderNoAction:
                self.setRepeatAction(
                    self._page_action(),
                    self._repeat_threshold,
                    self._repeat_time,
                )
            return

        self._update_active_subcontrols(pos)

    def mouseReleaseEvent(self, event) -> None:
        SC = QStyle.SubControl
        if self._pressed_subcontrol == SC.SC_None:
            event.ignore()
            return

        event.accept()
        self.setRepeatAction(QScrollBar.SliderAction.SliderNoAction)
        if self.isSliderDown():
            self.setSliderDown(False)
        self._pressed_subcontrol = SC.SC_None
        self._page_press_pos = None
        self._update_active_subcontrols(event.pos())
        self.update()

    def sliderChange(self, change) -> None:
        super().sliderChange(change)
        # Stop page stepping once the slider has reached the cursor.
        if (
            self._page_press_pos is not None
            and self._hit_test(self._page_press_pos)
            != self._pressed_subcontrol
        ):
            self.setRepeatAction(QScrollBar.SliderAction.SliderNoAction)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._active_subcontrols != QStyle.SubControl.SC_None:
            self._active_subcontrols = QStyle.SubControl.SC_None
            self.update()

    def _style_option(self) -> QStyleOptionSlider:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return option

    def _hit_test(self, pos: QPoint) -> QStyle.SubControl:
        return get_ayon_style().hitTestComplexControl(
            QStyle.ComplexControl.CC_ScrollBar,
            self._style_option(),
            pos,
            self,
        )

    def _page_action(self) -> QScrollBar.SliderAction:
        if self._pressed_subcontrol == QStyle.SubControl.SC_ScrollBarSubPage:
            return QScrollBar.SliderAction.SliderPageStepSub
        return QScrollBar.SliderAction.SliderPageStepAdd

    def _pos_along(self, pos: QPoint) -> int:
        """Logical position of ``pos`` along the scrollbar's orientation."""
        if self.orientation() == Qt.Orientation.Horizontal:
            return QStyle.visualPos(
                self.layoutDirection(), self.rect(), pos
            ).x()
        return pos.y()

    def _slider_span(self) -> tuple[int, int]:
        """Logical (start, length) of the slider along the orientation."""
        option = self._style_option()
        rect = QStyle.visualRect(
            option.direction,
            option.rect,
            get_ayon_style().subControlRect(
                QStyle.ComplexControl.CC_ScrollBar,
                option,
                QStyle.SubControl.SC_ScrollBarSlider,
                self,
            ),
        )
        if self.orientation() == Qt.Orientation.Horizontal:
            return rect.x(), rect.width()
        return rect.y(), rect.height()

    def _pixel_to_value(self, pos: QPoint) -> int:
        """Slider value for dragging the slider to ``pos``."""
        _start, length = self._slider_span()
        if self.orientation() == Qt.Orientation.Horizontal:
            groove_length = self.width()
        else:
            groove_length = self.height()
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            self._pos_along(pos) - self._click_offset,
            groove_length - length,
            self._style_option().upsideDown,
        )

    def _update_active_subcontrols(self, pos: QPoint) -> None:
        active_sub_controls = self._hit_test(pos)
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
