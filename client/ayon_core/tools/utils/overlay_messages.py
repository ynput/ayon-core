from __future__ import annotations

import uuid

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib import MaterialSymbolsIcon
from ayon_core.style import get_objected_colors

from .lib import set_style_property, get_qt_icon

# Material Symbols icon name by message type
_ICON_NAMES_BY_TYPE = {
    "success": "check_circle",
    "error": "error",
    "info": "info",
}


class CloseButton(QtWidgets.QFrame):
    """Close button drawed manually."""

    clicked = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        colors = get_objected_colors("overlay-messages")
        self._color = colors["close-btn"].get_qcolor()
        self._hover_color = colors["close-btn-hover"].get_qcolor()
        self._hover_bg_color = colors["close-btn-bg-hover"].get_qcolor()
        self._mouse_pressed = False
        # Trigger repaint on mouse enter and leave
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed
        )
        self.setSizePolicy(policy)

    def sizeHint(self):
        size = self.fontMetrics().height()
        return QtCore.QSize(size, size)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._mouse_pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed:
            self._mouse_pressed = False
            if self.rect().contains(event.pos()):
                self.clicked.emit()

        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        rect = self.rect()
        painter = QtGui.QPainter(self)
        painter.setClipRect(event.rect())
        color = self._color
        if self.underMouse():
            color = self._hover_color
            radius = rect.height() * 0.2
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self._hover_bg_color)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        pen = QtGui.QPen()
        pen.setWidth(2)
        pen.setColor(color)
        pen.setStyle(QtCore.Qt.SolidLine)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        offset = int(rect.height() / 4)
        top = rect.top() + offset
        left = rect.left() + offset
        right = rect.right() - offset
        bottom = rect.bottom() - offset
        painter.drawLine(
            left, top,
            right, bottom
        )
        painter.drawLine(
            left, bottom,
            right, top
        )


class OverlayMessageWidget(QtWidgets.QFrame):
    """Message widget showed as overlay.

    Message type is shown with colored icon and with progress bar at the
    bottom which is filling until the message is hidden.

    Message is hidden after timeout. The timeout is paused while mouse is
    hovering over the widget.

    Args:
        message_id (str): Unique identifier of message widget for
            'MessageOverlayObject'.
        message (str): Text shown in message.
        parent (QWidget): Parent widget where message is visible.
        timeout (int): Timeout of message's visibility (default 5000).
        message_type (str): Property which can be used in styles for specific
            kid of message.
    """

    close_requested = QtCore.Signal(str)
    _default_timeout = 5000
    _progress_height = 3

    def __init__(
        self, message_id, message, parent, message_type=None, timeout=None
    ):
        super().__init__(parent)
        self.setObjectName("OverlayMessageWidget")

        if message_type:
            set_style_property(self, "type", message_type)

        if not timeout:
            timeout = self._default_timeout

        # Animation is used as timeout and to paint the progress bar
        progress_anim = QtCore.QVariantAnimation(self)
        progress_anim.setStartValue(0.0)
        progress_anim.setEndValue(1.0)
        progress_anim.setDuration(timeout)

        icon_label = QtWidgets.QLabel(self)
        label_widget = QtWidgets.QLabel(message, self)
        label_widget.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        label_widget.setWordWrap(True)
        close_btn = CloseButton(self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4 + self._progress_height)
        layout.setSpacing(6)
        layout.addWidget(icon_label, 0)
        layout.addWidget(label_widget, 1)
        layout.addWidget(close_btn, 0)

        close_btn.clicked.connect(self._on_close_clicked)
        progress_anim.valueChanged.connect(self._on_progress_change)
        progress_anim.finished.connect(self._close_message)

        self._icon_label = icon_label
        self._label_widget = label_widget
        self._message_id = message_id
        self._progress_anim = progress_anim
        self._type_color = QtGui.QColor()

        self._update_message_type(message_type)

    def update_message(self, message, message_type=None, timeout=None):
        self._label_widget.setText(message)
        self._progress_anim.stop()
        if timeout:
            self._progress_anim.setDuration(timeout)

        set_style_property(self, "type", message_type)
        self._update_message_type(message_type)

        self._start_progress()

    def size_hint_without_word_wrap(self):
        """Size hint in cases that word wrap of label is disabled."""
        self._label_widget.setWordWrap(False)
        size_hint = self.sizeHint()
        self._label_widget.setWordWrap(True)
        return size_hint

    def showEvent(self, event):
        """Start timeout on show."""
        super().showEvent(event)
        self._progress_anim.stop()
        self._start_progress()

    def paintEvent(self, event):
        """Paint progress bar at the bottom of the message."""
        super().paintEvent(event)
        progress = self._progress_anim.currentValue()
        if not progress:
            return

        rect = QtCore.QRectF(self.rect())
        bar_rect = QtCore.QRectF(
            rect.left(),
            rect.bottom() - self._progress_height,
            rect.width() * progress,
            self._progress_height,
        )
        # Clip the bar to rounded corners of the widget
        # - radius should match 'border-radius' in stylesheets (0.2em)
        radius = self.fontMetrics().height() * 0.2
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setClipPath(clip_path)
        painter.fillRect(bar_rect, self._type_color)
        painter.end()

    def _update_message_type(self, message_type: str | None) -> None:
        """Change icon and color of progress bar by message type."""
        if message_type not in _ICON_NAMES_BY_TYPE:
            message_type = "success"
        color = get_objected_colors(
            "overlay-messages", message_type
        ).get_qcolor()
        icon = get_qt_icon(MaterialSymbolsIcon(
            _ICON_NAMES_BY_TYPE[message_type],
            color=color.name(),
            fill=True,
        ))
        # Make sure font from stylesheets is used to calculate icon size
        self.ensurePolished()
        icon_size = self.fontMetrics().height() + 2
        self._icon_label.setFixedSize(icon_size, icon_size)
        self._icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
        self._type_color = color
        self.update()

    def _start_progress(self) -> None:
        self._progress_anim.start()
        # Timeout does not run while mouse is over the widget
        if self.underMouse():
            self._progress_anim.pause()

    def _on_progress_change(self, _value: float) -> None:
        rect = self.rect()
        rect.setTop(rect.bottom() - self._progress_height)
        self.update(rect)

    def _on_close_clicked(self):
        self._close_message()

    def _close_message(self):
        """Emmit close request to 'MessageOverlayObject'."""
        self.close_requested.emit(self._message_id)

    def enterEvent(self, event):
        """Pause timeout on hover."""
        super().enterEvent(event)
        if self._progress_anim.state() == QtCore.QAbstractAnimation.Running:
            self._progress_anim.pause()

    def leaveEvent(self, event):
        """Continue with timeout on hover leave."""
        super().leaveEvent(event)
        if self._progress_anim.state() == QtCore.QAbstractAnimation.Paused:
            self._progress_anim.resume()


class MessageOverlayObject(QtCore.QObject):
    """Object that can be used to add overlay messages.

    Args:
        widget (QWidget):
    """

    def __init__(self, widget, default_timeout=None):
        super().__init__()

        widget.installEventFilter(self)

        # Timer which triggers recalculation of message positions
        recalculate_timer = QtCore.QTimer()
        recalculate_timer.setInterval(10)

        recalculate_timer.timeout.connect(self._recalculate_positions)

        self._widget = widget
        self._recalculate_timer = recalculate_timer

        self._messages_order = []
        self._closing_messages = set()
        self._messages = {}
        self._spacing = 5
        self._move_size = 4
        self._move_size_remove = 8
        self._default_timeout = default_timeout

    def add_message(
        self, message, message_type=None, timeout=None, message_id=None
    ):
        """Add single message into overlay.

        Args:
            message (str): Message that will be shown.
            timeout (int): Message timeout.
            message_type (str): Message type can be used as property in
                stylesheets.
            message_id (str): UUID of already existing message to update
                it's message and timeout. Is created with different id if is
                not available anymore.

        Returns:
            str: UUID of message which can be used to update message.
        """
        # Skip empty messages
        if not message:
            return

        if timeout is None:
            timeout = self._default_timeout

        # Create unique id of message
        widget = None
        if message_id is not None:
            widget = self._messages.get(message_id)

        if message_id is None:
            message_id = str(uuid.uuid4())

        elif message_id in self._messages_order:
            self._messages_order.remove(message_id)

        if widget is not None:
            # NOTE: Update of message won't change paint order which should be
            #   ok in most of cases as it matters only when messages are
            #   animated
            widget.update_message(message, message_type, timeout)
        else:
            # Create message widget
            widget = OverlayMessageWidget(
                message_id, message, self._widget, message_type, timeout
            )
            widget.close_requested.connect(self._on_message_close_request)
            widget.show()

        # Move widget outside of window
        pos = widget.pos()
        pos.setY(pos.y() - widget.height())
        widget.move(pos)
        # Store message
        self._messages[message_id] = widget
        self._messages_order.append(message_id)
        # Trigger recalculation timer
        self._recalculate_timer.start()

        return message_id

    def _on_message_close_request(self, message_id):
        """Message widget requested removement."""

        widget = self._messages.get(message_id)
        if widget is not None:
            # Add message to closing messages and start recalculation
            self._closing_messages.add(message_id)
            self._recalculate_timer.start()

    def _recalculate_positions(self):
        """Recalculate positions of widgets."""

        # Skip if there are no messages to process
        if not self._messages_order:
            self._recalculate_timer.stop()
            return

        # All message widgets are in expected positions
        all_at_place = True
        # Starting y position
        pos_y = self._spacing
        # Current widget width
        widget_width = self._widget.width()
        max_width = widget_width - (2 * self._spacing)
        widget_half_width = widget_width / 2

        # Store message ids that should be removed
        message_ids_to_remove = set()
        for message_id in reversed(self._messages_order):
            widget = self._messages[message_id]
            pos = widget.pos()
            # Messages to remove are moved upwards
            if message_id in self._closing_messages:
                bottom = pos.y() + widget.height()
                # Add message to remove if is not visible
                if bottom < 0 or self._move_size_remove < 1:
                    message_ids_to_remove.add(message_id)
                    continue

                # Calculate new y position of message
                dst_pos_y = pos.y() - self._move_size_remove

            else:
                # Calculate y position of message
                # - use y position of previous message widget and add
                #   move size if is not in final destination yet
                if widget.underMouse():
                    dst_pos_y = pos.y()
                elif pos.y() == pos_y or self._move_size < 1:
                    dst_pos_y = pos_y
                elif pos.y() < pos_y:
                    dst_pos_y = min(pos_y, pos.y() + self._move_size)
                else:
                    dst_pos_y = max(pos_y, pos.y() - self._move_size)

            # Store if widget is in place where should be
            if all_at_place and dst_pos_y != pos_y:
                all_at_place = False

            # Calculate ideal width and height of message widget
            height = widget.heightForWidth(max_width)
            w_size_hint = widget.size_hint_without_word_wrap()
            widget.resize(min(max_width, w_size_hint.width()), height)

            # Center message widget
            size = widget.size()
            pos_x = widget_half_width - (size.width() / 2)
            # Move widget to destination position
            widget.move(pos_x, dst_pos_y)

            # Add message widget height and spacing for next message widget
            pos_y += size.height() + self._spacing

        # Remove widgets to remove
        for message_id in message_ids_to_remove:
            self._messages_order.remove(message_id)
            self._closing_messages.remove(message_id)
            widget = self._messages.pop(message_id)
            widget.hide()
            widget.deleteLater()

        # Stop recalculation timer if all widgets are where should be
        if all_at_place:
            self._recalculate_timer.stop()

    def eventFilter(self, source, event):
        # Trigger recalculation of timer on resize of widget
        if source is self._widget and event.type() == QtCore.QEvent.Resize:
            self._recalculate_timer.start()

        return super().eventFilter(source, event)
