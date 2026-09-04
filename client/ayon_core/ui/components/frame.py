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
        hover_enabled=False,
        **kwargs,
    ):
        # Convert enum to string if needed
        self._bg: bool = bg
        self._variant_str = variant.value
        self._bg_tint = bg_tint
        self._bg_color = None
        self._hover_enabled = hover_enabled

        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())

        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        if hover_enabled:
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
            self.setMouseTracking(True)
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

    def _set_row_state_bit(
        self, bit: QtWidgets.QStyle.StateFlag, on: bool
    ) -> None:
        state = self.property("row_state") or QtWidgets.QStyle.StateFlag.State_None
        state = (state | bit) if on else (state & ~bit)
        self.setProperty("row_state", state)
        self.update()

    def set_selected(self, selected: bool) -> None:
        """Mark this frame as selected via the ``row_state`` property.

        The frame drawer reads this to pick the current variant's
        ``selected`` style block (background, border, ...), so a whole
        frame can carry a highlight the way a single-row control would,
        instead of only an inner button doing so.
        """
        self._set_row_state_bit(
            QtWidgets.QStyle.StateFlag.State_Selected, selected
        )

    def set_hovered(self, hovered: bool) -> None:
        """Mark this frame as hovered via the ``row_state`` property.

        Companion to :meth:`set_selected`: driven explicitly (see
        :class:`RowHoverTracker`) instead of relying on
        ``underMouse()``, since an interactive ``QPushButton`` child
        sitting on top of the frame doesn't reliably cascade hover
        state to it.
        """
        self._set_row_state_bit(
            QtWidgets.QStyle.StateFlag.State_MouseOver, hovered
        )


class RowHoverTracker(QtCore.QObject):
    """Keeps an :class:`AYFrame` hover-highlighted via ``set_hovered``.

    Install on the frame itself *and* on each interactive child
    (buttons) it contains, via :meth:`watch`. A ``QPushButton`` child
    can intercept mouse tracking in a way that prevents Qt's own
    Enter/Leave events from reliably reaching an ancestor frame, so
    this tracks hover directly instead of depending on that
    propagation.

    On every Leave from any watched widget, it re-checks the actual
    cursor position against the frame's own rect rather than assuming
    "left a child" means "left the frame" — moving from one child to a
    sibling (or to the frame's own background) fires a Leave too, and
    naively clearing hover on that would flicker or stick off.
    """

    def __init__(self, frame: AYFrame) -> None:
        super().__init__(frame)
        self._frame = frame

    def watch(self, *widgets: QtWidgets.QWidget) -> "RowHoverTracker":
        for widget in (self._frame, *widgets):
            widget.installEventFilter(self)
        return self

    def eventFilter(
        self, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if event.type() == QtCore.QEvent.Type.Enter:
            self._frame.set_hovered(True)
        elif event.type() == QtCore.QEvent.Type.Leave:
            local = self._frame.mapFromGlobal(QtGui.QCursor.pos())
            if not self._frame.rect().contains(local):
                self._frame.set_hovered(False)
        return False  # never consume the event
