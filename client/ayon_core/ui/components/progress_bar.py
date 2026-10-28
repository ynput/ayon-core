"""Determinate and indeterminate progress bar drawn in the AYON style."""

from __future__ import annotations

from enum import Enum

from qtpy.QtCore import QRectF, QSize, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QShowEvent,
)
from qtpy.QtWidgets import QSizePolicy, QWidget

from ..style_types import StyleDict, get_ayon_style
from ..variants import AYProgressBarVariants
from .style_mixin import StyleMixin


class ProgressBarState(Enum):
    """Semantic state controlling the colour of the filled chunk."""

    Normal = "normal"
    Error = "error"
    Warning = "warning"
    Success = "success"


class AYProgressBar(StyleMixin, QWidget):
    """Determinate and indeterminate progress bar in the AYON style.

    The bar is empty while ``maximum`` is ``0``, and indeterminate (a
    sweeping chunk) while ``value`` or ``maximum`` is negative.

    By default the percentage is drawn right of the track. Its space is
    reserved also while indeterminate, so the track does not change width
    when the text appears or disappears. Pass ``show_value=False`` for a
    bar without text.

    Args:
        parent: Parent widget.
        maximum: Value that represents a full bar.
        variant: Visual style variant.
        show_value: Whether the percentage is drawn next to the track.

    Signals:
        value_changed (int): Current value.
        maximum_changed (int): Current maximum.

    """
    value_changed = Signal(int)
    maximum_changed = Signal(int)

    #: Style token used to colour the chunk for each semantic state.
    _STATE_COLOR_KEY = {
        ProgressBarState.Normal: "chunk-color",
        ProgressBarState.Success: "success-color",
        ProgressBarState.Warning: "warning-color",
        ProgressBarState.Error: "failed-color",
    }

    #: Milliseconds for the indeterminate chunk to cross the whole bar.
    _SWEEP_DURATION_MS = 1200

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        maximum: int = 0,
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
        show_value: bool = True,
    ) -> None:
        super().__init__(parent)
        self._variant_str = variant.value
        self._style_data = StyleDict()

        self._value: int = 0
        self._maximum: int = maximum
        self._state: ProgressBarState = ProgressBarState.Normal
        self._show_value: bool = show_value

        # Offset of the indeterminate sweep animation, not progress data.
        self._sweep = 0.0

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        _style = get_ayon_style()
        self.setStyle(_style)
        self._style_data = _style.model.get_styles(
            "AYProgressBar", variant=self._variant_str
        )
        self._style_data.set_context(self)

        # The sweep animation only runs while indeterminate AND visible.
        self._timer = QTimer(self)
        self._timer.setInterval(self._animation_interval())
        self._timer.timeout.connect(self._advance_sweep)

    def value(self) -> int:
        """Return the current value."""
        return self._value

    def maximum(self) -> int:
        """Return the value that represents a full bar."""
        return self._maximum

    def set_value(self, value: int) -> None:
        """Set the current value, negative makes the bar indeterminate."""
        if value == self._value:
            return
        self._value = value
        self._update_animation()
        self.update()
        self.value_changed.emit(self._value)

    def set_maximum(self, value: int) -> None:
        """Set the full-bar value, negative makes the bar indeterminate."""
        if value == self._maximum:
            return
        self._maximum = value
        self._update_animation()
        self.update()
        self.maximum_changed.emit(self._maximum)

    def state(self) -> ProgressBarState:
        """Return the semantic state used to colour the chunk."""
        return self._state

    def set_state(self, state: ProgressBarState) -> None:
        """Set the semantic state used to colour the chunk."""
        if state == self._state:
            return
        self._state = state
        self.update()

    def is_indeterminate(self) -> bool:
        """True while the progress cannot be shown as a fraction."""
        return self._value < 0 or self._maximum < 0

    def is_animating(self) -> bool:
        """True while the indeterminate sweep timer is running."""
        return self._timer.isActive()

    def percentage(self) -> float:
        """Return the completion percentage in the ``0.0``-``100.0`` range."""
        if self.is_indeterminate() or self._maximum == 0:
            return 0.0
        fraction = self._value / self._maximum
        return max(0.0, min(fraction, 1.0)) * 100.0

    def text(self) -> str:
        """Return the percentage text, empty while indeterminate."""
        if self.is_indeterminate():
            return ""
        return f"{self.percentage():.0f}%"

    def show_value(self) -> bool:
        """Return whether the percentage is drawn next to the track."""
        return self._show_value

    def set_show_value(self, show_value: bool) -> None:
        """Set whether the percentage is drawn next to the track."""
        if show_value == self._show_value:
            return
        self._show_value = show_value
        self.updateGeometry()
        self.update()

    def _base_style(self) -> StyleDict:
        """Return the colours and geometry shared by every state.

        ``base`` is the only dict carrying the visual properties; the
        per-state dicts (``disabled``) hold deltas such as ``opacity``
        and must not replace it.

        Returns:
            The style tokens for the widget's base appearance.
        """
        return self._style_data.get("base") or StyleDict()

    def _opacity(self) -> float:
        """Return the opacity for the current state.

        The ``disabled`` state only overrides ``opacity``, so it is read
        separately from the base colours and applied in ``paintEvent``.
        """
        if self.isEnabled():
            return 1.0
        disabled = self._style_data.get("disabled")
        if disabled is None:
            return 1.0
        try:
            return float(disabled.get("opacity", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _animation_interval(self) -> int:
        """Return the sweep timer interval in milliseconds."""
        value = self._base_style().get("animation-interval-ms", 16)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 16

    def _advance_sweep(self) -> None:
        """Advance the indeterminate sweep and repaint."""
        step = self._timer.interval() / self._SWEEP_DURATION_MS
        self._sweep = (self._sweep + step) % 1.0
        self.update()

    def _update_animation(self) -> None:
        """Start the sweep timer while indeterminate and visible."""
        if self.is_indeterminate() and self.isVisible():
            if not self._timer.isActive():
                self._sweep = 0.0
                self._timer.start()
        else:
            self._timer.stop()

    # --- painting
    def _chunk_color(self, style: StyleDict) -> QColor:
        """Return the chunk colour for the current semantic state."""
        key = self._STATE_COLOR_KEY.get(self.state(), "chunk-color")
        color = style.get(key) or style.get("chunk-color", "#8fceff")
        return QColor(color)

    def _value_width(self, style: StyleDict) -> int:
        """Return the width reserved for the percentage text."""
        if not self._show_value:
            return 0
        text_width = self.fontMetrics().horizontalAdvance("100%")
        return max(int(style.get("value-min-width", 40)), text_width)

    def _value_space(self, style: StyleDict) -> int:
        """Return the total width taken by the text and its spacing."""
        value_width = self._value_width(style)
        if not value_width:
            return 0
        return value_width + int(style.get("value-spacing", 6))

    def _draw_value(self, painter: QPainter, style: StyleDict) -> None:
        """Draw the percentage right-aligned at the right edge.

        Args:
            painter: Painter configured for this widget.
            style: Style tokens for the current state.
        """
        text = self.text()
        if not self._show_value or not text:
            return
        margin = float(style.get("margin", 0))
        value_width = self._value_width(style)
        rect = QRectF(
            self.width() - margin - value_width,
            0,
            value_width,
            self.height(),
        )
        # Same colour as a dim ``AYLabel``.
        painter.setPen(
            self.palette().color(QPalette.ColorRole.PlaceholderText)
        )
        painter.setFont(self.font())
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            text,
        )

    def _draw_bar(self, painter: QPainter, style: StyleDict) -> None:
        """Draw the track and the filled or sweeping chunk.

        Args:
            painter: Painter configured for this widget.
            style: Style tokens for the current state.
        """
        height = float(style.get("height", 6))
        margin = float(style.get("margin", 0))
        width = self.width() - margin * 2 - self._value_space(style)
        if width <= 0 or height <= 0:
            return

        radius = min(float(style.get("radius", height / 2.0)), height / 2.0)
        top = (self.height() - height) / 2.0
        track = QRectF(margin, top, width, height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(style.get("track-color", "#41474d")))
        painter.drawRoundedRect(track, radius, radius)

        if self.is_indeterminate():
            chunk_w = width * float(style.get("sweep-ratio", 0.3))
            x = track.x() - chunk_w + self._sweep * (width + chunk_w)
            chunk = QRectF(x, top, chunk_w, height)
            painter.save()
            painter.setClipRect(track)
            painter.setBrush(self._chunk_color(style))
            painter.drawRoundedRect(chunk, radius, radius)
            painter.restore()
        elif self._value > 0:
            chunk_w = width * (self.percentage() / 100.0)
            chunk = QRectF(track.x(), top, chunk_w, height)
            painter.setBrush(self._chunk_color(style))
            painter.drawRoundedRect(chunk, radius, radius)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the track, the chunk, and the optional percentage.

        Descriptive text, such as a caption, belongs to the owner.

        Args:
            event: The paint event; the whole widget is repainted.
        """
        style = self._base_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity())
        self._draw_bar(painter, style)
        self._draw_value(painter, style)
        painter.end()

    def sizeHint(self) -> QSize:
        """Return the preferred size derived from the style height."""
        style = self._base_style()
        height = int(style.get("height", 6))
        if self._show_value:
            height = max(height, self.fontMetrics().height())
        return QSize(200 + self._value_space(style), height)

    def minimumSizeHint(self) -> QSize:
        """Return the minimum size derived from the style height."""
        style = self._base_style()
        return QSize(
            40 + self._value_space(style), self.sizeHint().height()
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)
