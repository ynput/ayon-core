"""Overlay showing that connection to AYON server was lost."""
from __future__ import annotations

import math

from qtpy import QtWidgets, QtCore, QtGui


class AYONLogoAnimation(QtWidgets.QWidget):
    """Animated AYON 'Y' symbol (three bars and a dot).

    Mimics loader animation of AYON web ('LoadingPage' in ayon-frontend).
        The dot bounces while the whole symbol pulses and once per two
        bounces does a full turn. Symbol is scaled to fit the widget size.

    Animation runs only while the widget is visible and active.

    """
    # Proportions of the 'Y' symbol relative to the bar length,
    #   taken from the AYON logo svg
    _bar_width_ratio: float = 0.2727
    # Gap between center of the symbol and the inner end of a bar
    _bar_gap_ratio: float = 0.3121
    _dot_radius_ratio: float = 0.2727
    _dot_distance_ratio: float = 1.0469
    # How high the dot jumps
    _jump_ratio: float = 0.716
    _opacity: float = 0.8

    # Duration of symbol pulse, the dot bounces twice per pulse
    _anim_duration: int = 1400
    # Animation does not start from the beginning (normalized 0.0 - 1.0)
    _anim_offset: float = 1.0 / 1.4
    # Keyframes as (progress, value) of the pulse
    _scale_keyframes = (
        (0.0, 1.0), (0.25, 0.9), (0.5, 1.0), (0.75, 0.7), (1.0, 1.0)
    )
    _rotation_keyframes = (
        (0.0, 0.0), (0.65, 0.0), (0.95, 360.0), (1.0, 360.0)
    )
    # Keyframes of one bounce, value is jump height ratio
    _jump_keyframes = ((0.0, 1.0), (0.5, 0.0), (1.0, 1.0))

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

        # Easing curves used in web
        ease_in_out = QtCore.QEasingCurve(QtCore.QEasingCurve.BezierSpline)
        ease_in_out.addCubicBezierSegment(
            QtCore.QPointF(0.42, 0.0),
            QtCore.QPointF(0.58, 1.0),
            QtCore.QPointF(1.0, 1.0),
        )
        bounce_ease = QtCore.QEasingCurve(QtCore.QEasingCurve.BezierSpline)
        bounce_ease.addCubicBezierSegment(
            QtCore.QPointF(0.58, 0.01),
            QtCore.QPointF(0.44, 0.97),
            QtCore.QPointF(1.0, 1.0),
        )

        self._anim = anim
        self._progress: float = 0.0
        self._ease_in_out = ease_in_out
        self._bounce_ease = bounce_ease
        self._bar_length: int = bar_length
        self._active: bool = True
        # Bounds of the symbol during whole animation relative to
        #   the symbol center in bar length units
        self._bounds: QtCore.QRectF = self._calculate_bounds()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )

    def sizeHint(self):
        return QtCore.QSize(
            math.ceil(self._bar_length * self._bounds.width()),
            math.ceil(self._bar_length * self._bounds.height()),
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
                self._progress = 0.0
                self._anim.start()
            return

        if is_running:
            self._anim.stop()

    def _on_anim_value(self, value):
        self._progress = float(value)
        self.update()

    def _get_keyframe_value(
        self,
        keyframes: tuple[tuple[float, float], ...],
        progress: float,
        easing: QtCore.QEasingCurve,
    ) -> float:
        """Interpolate keyframes, easing is applied to each segment."""
        prev_pos, prev_value = keyframes[0]
        for pos, value in keyframes[1:]:
            if progress <= pos:
                ratio = (progress - prev_pos) / (pos - prev_pos)
                ratio = easing.valueForProgress(ratio)
                return prev_value + (value - prev_value) * ratio
            prev_pos, prev_value = pos, value
        return prev_value

    def _get_anim_values(
        self, progress: float
    ) -> tuple[float, float, float]:
        """Values of animation for passed progress.

        Args:
            progress (float): Animation progress (0.0-1.0).

        Returns:
            tuple[float, float, float]: Jump height ratio (0.0-1.0),
                symbol rotation in degrees and symbol scale.

        """
        progress = (progress + self._anim_offset) % 1.0
        bounce_progress = (progress * 2.0) % 1.0
        jump = self._get_keyframe_value(
            self._jump_keyframes, bounce_progress, self._bounce_ease
        )
        rotation = self._get_keyframe_value(
            self._rotation_keyframes, progress, self._ease_in_out
        )
        scale = self._get_keyframe_value(
            self._scale_keyframes, progress, self._ease_in_out
        )
        return jump, rotation, scale

    def _calculate_bounds(self) -> QtCore.QRectF:
        """Bounds of the symbol during whole animation.

        The symbol does not stay in the same area during the animation,
            so the bounds are found by sampling the animation.

        """
        bar_rect = QtCore.QRectF(
            -self._bar_width_ratio * 0.5,
            self._bar_gap_ratio,
            self._bar_width_ratio,
            1.0,
        )
        bounds = QtCore.QRectF()
        samples = 200
        for idx in range(samples):
            jump, rotation, scale = self._get_anim_values(idx / samples)
            transform = QtGui.QTransform()
            transform.rotate(rotation)
            transform.scale(scale, scale)
            for bar_idx in range(3):
                bar_transform = QtGui.QTransform()
                bar_transform.rotate(120 * bar_idx)
                bounds |= (bar_transform * transform).mapRect(bar_rect)
            dot_center = transform.map(QtCore.QPointF(
                0.0,
                -(self._dot_distance_ratio + self._jump_ratio * jump),
            ))
            radius = self._dot_radius_ratio * scale
            bounds |= QtCore.QRectF(
                dot_center.x() - radius,
                dot_center.y() - radius,
                radius * 2,
                radius * 2,
            )
        return bounds

    def paintEvent(self, event):
        rect = self.rect()
        bounds = self._bounds
        bar_length = min(
            float(self._bar_length),
            rect.height() / bounds.height(),
            rect.width() / bounds.width(),
        )
        if bar_length < 4:
            return

        jump, rotation, scale = 0.0, 0.0, 1.0
        if self._active:
            jump, rotation, scale = self._get_anim_values(self._progress)

        bar_width = bar_length * self._bar_width_ratio
        bar_gap = bar_length * self._bar_gap_ratio
        dot_radius = bar_length * self._dot_radius_ratio

        # Center the animation bounds in the widget
        center = QtCore.QPointF(
            (
                rect.x()
                + (rect.width() - bar_length * bounds.width()) * 0.5
                - bar_length * bounds.x()
            ),
            (
                rect.y()
                + (rect.height() - bar_length * bounds.height()) * 0.5
                - bar_length * bounds.y()
            ),
        )

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setOpacity(self._opacity)
        painter.translate(center)
        painter.rotate(rotation)
        painter.scale(scale, scale)

        # Bar pointing down, other two are rotated by 120 degrees
        painter.save()
        painter.setBrush(self._bars_color)
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
        dot_color = self._dot_color
        if not self._active:
            dot_color = self._dot_inactive_color
        painter.setBrush(dot_color)
        painter.drawEllipse(QtCore.QPointF(0, dot_y), dot_radius, dot_radius)
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
            text = "AYON server is restarting..."
        else:
            text = "Connection to AYON server lost..."
        self._message_label.setText(text)
