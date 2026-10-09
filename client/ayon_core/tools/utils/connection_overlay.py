"""Overlay showing that connection to AYON server was lost."""
from __future__ import annotations

import math

from qtpy import QtWidgets, QtCore, QtGui


class AYONLogoAnimation(QtWidgets.QWidget):
    """Animated AYON 'Y' symbol (three bars and a dot).

    The dot bounces and while it is in the air the bars rotate by
        120 degrees, so on landing the symbol looks the same as at
        the start. Symbol is scaled to fit the widget size.

    Animation runs only while the widget is visible and active.

    """
    # Proportions of the 'Y' symbol relative to the bar length,
    #   taken from the AYON logo
    _bar_width_ratio: float = 0.277
    # Gap between center of the symbol and the inner end of a bar
    _bar_gap_ratio: float = 0.315
    _dot_radius_ratio: float = 0.273
    _dot_distance_ratio: float = 1.05
    # How high the dot jumps
    _jump_ratio: float = 1.0
    # Extents of the animated symbol from its center
    _top_extent_ratio: float = (
        _dot_distance_ratio + _dot_radius_ratio + _jump_ratio
    )
    _bottom_extent_ratio: float = _bar_gap_ratio + 1.0
    # Width of the symbol (rotated bars)
    _width_ratio: float = (_bar_gap_ratio + 1.0) * 2

    _anim_duration: int = 700
    # Animation timeline (normalized 0.0 - 1.0)
    _jump_start: float = 0.1
    _jump_peak: float = 0.5
    _jump_end: float = 0.85
    _rotation_start: float = 0.15
    _rotation_end: float = 0.75

    _bars_color = QtGui.QColor(255, 255, 255)
    _dot_color = QtGui.QColor(0, 215, 160)
    _dot_inactive_color = QtGui.QColor(220, 90, 90)

    def __init__(self, parent=None, bar_length: int = 44):
        super().__init__(parent)

        anim = QtCore.QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._anim_duration)
        anim.setLoopCount(-1)
        anim.valueChanged.connect(self._on_anim_value)

        self._anim = anim
        self._progress: float = 0.0
        self._ease_out = QtCore.QEasingCurve(QtCore.QEasingCurve.OutQuad)
        self._ease_in = QtCore.QEasingCurve(QtCore.QEasingCurve.InQuad)
        self._ease_in_out = QtCore.QEasingCurve(
            QtCore.QEasingCurve.InOutCubic
        )
        self._bar_length: int = bar_length
        self._active: bool = True

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )

    def sizeHint(self):
        height_ratio = self._top_extent_ratio + self._bottom_extent_ratio
        return QtCore.QSize(
            math.ceil(self._bar_length * self._width_ratio),
            math.ceil(self._bar_length * height_ratio),
        )

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def set_active(self, active: bool):
        """Inactive symbol does not animate and has red dot."""
        if self._active == active:
            return
        self._active = active
        self._update_animation()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_animation()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._update_animation()

    def _update_animation(self):
        should_run = self.isVisible() and self._active
        is_running = (
            self._anim.state() == QtCore.QAbstractAnimation.Running
        )
        if should_run:
            if not is_running:
                self._anim.start()
            return

        if is_running:
            self._anim.stop()
        # Show the symbol in its rest pose
        self._progress = 0.0

    def _on_anim_value(self, value):
        self._progress = float(value)
        self.update()

    def _get_anim_values(self) -> tuple[float, float, float, float]:
        """Values of animation for current progress.

        Returns:
            tuple[float, float, float, float]: Jump height ratio (0.0-1.0),
                bars rotation in degrees, symbol scale and dot squash.

        """
        progress = self._progress

        # Dot jump
        jump = 0.0
        if self._jump_start <= progress < self._jump_peak:
            value = (
                (progress - self._jump_start)
                / (self._jump_peak - self._jump_start)
            )
            jump = self._ease_out.valueForProgress(value)
        elif self._jump_peak <= progress < self._jump_end:
            value = (
                (progress - self._jump_peak)
                / (self._jump_end - self._jump_peak)
            )
            jump = 1.0 - self._ease_in.valueForProgress(value)

        # Bars rotation, rotation by 120 degrees looks the same as
        #   no rotation
        rotation = 0.0
        if self._rotation_start < progress < self._rotation_end:
            value = (
                (progress - self._rotation_start)
                / (self._rotation_end - self._rotation_start)
            )
            rotation = 120.0 * self._ease_in_out.valueForProgress(value)

        # Symbol squashes before jump (takeoff) and after landing
        squash = 0.0
        if progress < self._jump_start:
            squash = math.sin(progress / self._jump_start * math.pi)
        elif progress >= self._jump_end:
            value = (progress - self._jump_end) / (1.0 - self._jump_end)
            squash = math.sin(value * math.pi)
        scale = 1.0 - (0.08 * squash)

        return jump, rotation, scale, squash

    def paintEvent(self, event):
        rect = self.rect()
        height_ratio = self._top_extent_ratio + self._bottom_extent_ratio
        bar_length = min(
            float(self._bar_length),
            rect.height() / height_ratio,
            rect.width() / self._width_ratio,
        )
        if bar_length < 4:
            return

        jump, rotation, scale, squash = self._get_anim_values()

        bar_width = bar_length * self._bar_width_ratio
        bar_gap = bar_length * self._bar_gap_ratio
        dot_radius = bar_length * self._dot_radius_ratio
        bottom_offset = bar_length * self._bottom_extent_ratio

        # Center the symbol in the widget
        content_height = bar_length * height_ratio
        center = QtCore.QPointF(
            rect.center().x(),
            (
                rect.y()
                + (rect.height() - content_height) * 0.5
                + bar_length * self._top_extent_ratio
            ),
        )

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.translate(center)

        # Bars, squash is anchored to the bottom of the symbol
        painter.save()
        painter.translate(0, bottom_offset)
        painter.scale(1.0 + (1.0 - scale), scale)
        painter.translate(0, -bottom_offset)
        painter.rotate(rotation)
        painter.setBrush(self._bars_color)
        # Bar pointing down, other two are rotated by 120 degrees
        bar_rect = QtCore.QRectF(
            -bar_width * 0.5, bar_gap, bar_width, bar_length
        )
        for _ in range(3):
            painter.drawRect(bar_rect)
            painter.rotate(120)
        painter.restore()

        # Dot
        dot_y = -(
            bar_length * self._dot_distance_ratio
            + bar_length * self._jump_ratio * jump
        )
        # Follow the bars when they are squashed
        dot_y += bottom_offset * (1.0 - scale)
        dot_color = self._dot_color
        if not self._active:
            dot_color = self._dot_inactive_color
        painter.setBrush(dot_color)
        dot_squash = 0.15 * squash
        painter.drawEllipse(
            QtCore.QPointF(0, dot_y + dot_radius * dot_squash),
            dot_radius * (1.0 + dot_squash),
            dot_radius * (1.0 - dot_squash),
        )
        painter.end()


class ConnectionOverlay(QtWidgets.QWidget):
    """Overlay covering parent widget when AYON server is not reachable.

    The overlay follows size of the parent widget and shows itself when
        connection to AYON server is lost.

    Server events are received in a background thread. The overlay
        periodically calls 'controller.process_server_events' while
        the parent widget is visible, so the events are processed in
        the main thread.

    Controller must implement:
        - 'register_event_callback(topic, callback)'
        - 'process_server_events()'
        - 'get_server_connection_state()'

    Controller events (emitted by 'WSEventsModel'):
        - 'ayon.connection.opened'
        - 'ayon.connection.closed'
        - 'ayon.auth.failed'
        - 'ayon.server.restart'

    Args:
        controller (Any): Tool controller.
        parent (QtWidgets.QWidget): Widget that is covered by the overlay,
            usually tool window.

    """
    _bg_color = QtGui.QColor(37, 42, 48, 212)
    _process_interval: int = 200

    def __init__(self, controller, parent: QtWidgets.QWidget):
        super().__init__(parent)

        logo_widget = AYONLogoAnimation(self)

        message_label = QtWidgets.QLabel(self)
        message_label.setAlignment(QtCore.Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #ffffff;"
            " background: transparent;"
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addStretch(1)
        main_layout.addWidget(logo_widget, 0, QtCore.Qt.AlignHCenter)
        main_layout.addSpacing(16)
        main_layout.addWidget(message_label, 0)
        main_layout.addStretch(1)

        server_events_timer = QtCore.QTimer(self)
        server_events_timer.setInterval(self._process_interval)
        server_events_timer.timeout.connect(self._on_server_events_timer)

        controller.register_event_callback(
            "ayon.connection.opened",
            self._on_connection_opened,
        )
        controller.register_event_callback(
            "ayon.connection.closed",
            self._on_connection_closed,
        )
        controller.register_event_callback(
            "ayon.auth.failed",
            self._on_auth_failed,
        )
        controller.register_event_callback(
            "ayon.server.restart",
            self._on_server_restart,
        )

        self._controller = controller
        self._logo_widget = logo_widget
        self._message_label = message_label
        self._server_events_timer = server_events_timer

        self._server_restarting: bool = False
        self._auth_invalid: bool = False

        self._update_message()
        self.setVisible(False)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        if parent.isVisible():
            self._on_parent_show()

    def set_server_restarting(self, restarting: bool):
        self._server_restarting = restarting
        self._update_message()

    def set_invalid_authentication(self, invalid: bool):
        self._auth_invalid = invalid
        self._logo_widget.set_active(not invalid)
        self._update_message()

    def eventFilter(self, obj, event):
        if obj is self.parent():
            event_type = event.type()
            if event_type == QtCore.QEvent.Resize:
                self.setGeometry(obj.rect())
            elif event_type == QtCore.QEvent.Show:
                self._on_parent_show()
            elif event_type == QtCore.QEvent.Hide:
                self._server_events_timer.stop()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def _on_parent_show(self):
        self._server_events_timer.start()
        self._controller.process_server_events()
        if self._controller.get_server_connection_state() is False:
            self._show_overlay()

    def _on_server_events_timer(self):
        self._controller.process_server_events()

    def _show_overlay(self):
        # Make sure the overlay is above widgets created later
        self.raise_()
        self.setVisible(True)

    def _on_connection_opened(self):
        self.setVisible(False)
        self.set_invalid_authentication(False)
        self.set_server_restarting(False)

    def _on_connection_closed(self):
        self._show_overlay()

    def _on_auth_failed(self):
        self.set_invalid_authentication(True)
        self._show_overlay()

    def _on_server_restart(self):
        self.set_server_restarting(True)
        self._show_overlay()

    def _update_message(self):
        if self._auth_invalid:
            text = (
                "Authentication failed.\nPlease log in again"
                " and restart all applications."
            )
        elif self._server_restarting:
            text = "AYON server is restarting.."
        else:
            text = "Connection to AYON server lost.."
        self._message_label.setText(text)
