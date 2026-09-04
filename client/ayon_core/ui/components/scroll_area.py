"""scroll area"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QMouseEvent, QPainter, QPaintEvent
from qtpy.QtWidgets import (
    QFrame,
    QScrollArea,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
)

from ..style_types import get_ayon_style
from ..variants import QScrollBarVariants
from .style_mixin import StyleMixin


class AYScrollBar(StyleMixin, QScrollBar):
    """AYON styled scroll bar widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QTextEdit.
        variant: Visual variant — ``Default`` (opaque track, matches
            the table) or ``Transparent_Track`` (no track fill, just
            the thumb).
        **kwargs: Keyword arguments passed to QTextEdit.
    """

    Variants = QScrollBarVariants

    def __init__(
        self,
        *args,
        variant: QScrollBarVariants = QScrollBarVariants.Default,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._variant_str = variant.value
        self.setStyle(get_ayon_style())
        # The "default" variant's track fill happens to paint over the
        # widget's entire rect, masking that it has no real background
        # of its own. "transparent-track" skips that fill, which would
        # otherwise leave Qt's own opaque default widget background
        # showing through instead of whatever sits behind the scrollbar.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if variant == QScrollBarVariants.Transparent_Track:
            # QScrollBar sets this True by default: a hint that its
            # paintEvent always covers its whole rect opaquely, letting
            # Qt skip compositing whatever is behind it. The page/
            # add-page painting for this variant draws alpha 0, so
            # without clearing this the widget's region still resolves
            # to Qt's stale/opaque fallback instead of showing what's
            # actually behind the scrollbar. Only needed for this
            # variant — the default variant's track is opaque anyway,
            # and disabling the optimization there would only cost a
            # touch of antialiasing precision for nothing.
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._dragging = False
        self._drag_origin = 0
        self._drag_value = 0
        self._drag_range = 0

    def initStyleOption(self, option: QStyleOptionSlider) -> None:
        super().initStyleOption(option)
        SC = QStyle.SubControl
        option.subControls = (
            SC.SC_None
            | SC.SC_ScrollBarGroove
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Drag the painted thumb even when custom hit geometry differs."""
        if event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            slider_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_ScrollBar,
                option,
                QStyle.SubControl.SC_ScrollBarSlider,
                self,
            )
            # The custom drawer uses a thick pen, which extends the painted
            # thumb beyond Qt's slider hit rectangle. Add extra tolerance
            # along the drag axis so the whole visible thumb is draggable.
            minimum_length = self.style().pixelMetric(
                QStyle.PixelMetric.PM_ScrollBarSliderMin,
                option,
                self,
            )
            tolerance = max(42, minimum_length)
            if self.orientation() == Qt.Orientation.Vertical:
                hit_rect = slider_rect.adjusted(
                    -3, -tolerance, 3, tolerance
                )
            else:
                hit_rect = slider_rect.adjusted(
                    -tolerance, -3, tolerance, 3
                )
            position = event.pos()
            if hit_rect.contains(position):
                self._dragging = True
                self.grabMouse()
                self.setSliderDown(True)
                self._drag_origin = (
                    position.y()
                    if self.orientation() == Qt.Orientation.Vertical
                    else position.x()
                )
                self._drag_value = self.value()
                groove_rect = self.style().subControlRect(
                    QStyle.ComplexControl.CC_ScrollBar,
                    option,
                    QStyle.SubControl.SC_ScrollBarGroove,
                    self,
                )
                groove_length = (
                    groove_rect.height()
                    if self.orientation() == Qt.Orientation.Vertical
                    else groove_rect.width()
                )
                slider_length = (
                    slider_rect.height()
                    if self.orientation() == Qt.Orientation.Vertical
                    else slider_rect.width()
                )
                self._drag_range = max(1, groove_length - slider_length)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            position = event.pos()
            current = (
                position.y()
                if self.orientation() == Qt.Orientation.Vertical
                else position.x()
            )
            delta = current - self._drag_origin
            value_range = self.maximum() - self.minimum()
            value_delta = round(delta * value_range / self._drag_range)
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            if option.upsideDown:
                value_delta = -value_delta
            self.setValue(self._drag_value + value_delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.releaseMouse()
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AYScrollArea(StyleMixin, QScrollArea):
    """AYON styled scroll area widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QTextEdit.
        scrollbar_variant: Variant forwarded to the vertical/horizontal
            :class:`AYScrollBar` instances this area creates.
        **kwargs: Keyword arguments passed to QTextEdit.
    """

    Variants = QScrollBarVariants

    def __init__(
        self,
        *args,
        scrollbar_variant: QScrollBarVariants = QScrollBarVariants.Default,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())
        # AYONStyle's FrameDrawer would otherwise draw a 1px frame around the
        # viewport, which shows as a thin line on the right edge (above the
        # scrollbar) and along the bottom.
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.setVerticalScrollBar(
            AYScrollBar(Qt.Orientation.Vertical, variant=scrollbar_variant)
        )
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBar(
            AYScrollBar(Qt.Orientation.Horizontal, variant=scrollbar_variant)
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
