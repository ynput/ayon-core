"""Shared base class for floating dropdown popup widgets."""

from __future__ import annotations

from qtpy import QtGui, QtWidgets
from qtpy.QtCore import QPoint, Qt, Signal

from ..style import get_ayon_style
from ..variants import QFrameVariants
from .frame import AYFrame


class AYDropdownPopup(AYFrame):
    """Base class for floating dropdown popups.

    Provides:
    - Popup window flags (frameless, no drop shadow)
    - ``show_below(widget)`` positioning with screen-edge awareness
    - Escape key to close
    - ``popup_closed`` signal on close

    Attributes:
        Variants: Alias for ``QFrameVariants`` for consistent usage.
        popup_closed: Emitted when the popup is closed or hidden.
    """

    Variants = QFrameVariants

    popup_closed = Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        variant: Variants = AYFrame.Variants.Low,
        translucent_bg: bool = True,
    ) -> None:
        """Initialize the dropdown popup.

        Sets popup window flags and configures translucent background.

        Args:
            parent: Optional parent widget (used for style inheritance).
            variant: Frame style variant.
            translucent_bg: Whether to enable a translucent background.
                Set to ``False`` when the popup must be fully opaque.
        """
        super().__init__(parent, variant=variant)
        self.setStyle(get_ayon_style())
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_WindowPropagation)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, translucent_bg
        )

    def show_below(
        self,
        widget: QtWidgets.QWidget,
        y_offset: int = 2,
    ) -> None:
        """Position and show the popup below (or above) the widget.

        The popup is left-aligned with the widget's left edge.  If there
        is not enough horizontal space on screen the popup is shifted left.
        If there is not enough vertical space below, the popup is shown
        above the widget instead.

        Args:
            widget: The reference widget to position against.
            y_offset: Extra vertical gap (pixels) between the widget's
                bottom edge and the popup's top edge.  Defaults to ``2``.
        """
        global_pos = widget.mapToGlobal(QPoint(0, widget.height() + y_offset))
        self.adjustSize()

        screen = QtWidgets.QApplication.screenAt(global_pos)
        if screen:
            geo = screen.availableGeometry()

            # Shift left if popup would overflow right edge
            if global_pos.x() + self.width() > geo.right():
                global_pos.setX(geo.right() - self.width())

            # Show above if not enough vertical space below
            if global_pos.y() + self.height() > geo.bottom():
                above_y = widget.mapToGlobal(QPoint(0, 0)).y() - self.height()
                global_pos.setY(above_y)

        self.move(global_pos)
        self.show()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Close on Escape key; delegate all other keys to the parent.

        Args:
            event: The key event.
        """
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Emit ``popup_closed`` when the popup is hidden or closed.

        Args:
            event: The close event.
        """
        self.popup_closed.emit()
        super().closeEvent(event)
