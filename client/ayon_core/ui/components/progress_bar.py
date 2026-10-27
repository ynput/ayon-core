"""Determinate and indeterminate progress bar drawn in the AYON style."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from qtpy.QtCore import QRectF, QSize, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from qtpy.QtWidgets import QSizePolicy, QWidget

from ..style_types import StyleDict, get_ayon_style
from ..variants import AYProgressBarVariants
from .container import AYContainer
from .label import AYLabel
from .style_mixin import StyleMixin


class ProgressBarState(Enum):
    """Semantic state controlling the colour of the filled chunk."""

    Normal = "normal"
    Error = "error"
    Warning = "warning"
    Success = "success"


class AYProgressBar(StyleMixin, QWidget):
    """Determinate and indeterminate progress bar in the AYON style.

    Args:
        parent: Parent widget.
        variant: Visual style variant.

    Signals:
        progress_changed (int): Current value.

    """
    value_changed = Signal(int)

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
        maximum: int = 0,
        parent: QWidget | None = None,
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
    ) -> None:
        super().__init__(parent)
        self._variant_str = variant.value
        self._style_data = StyleDict()

        self._value: int = 0
        self._maximum: int = maximum
        self._state: ProgressBarState = ProgressBarState.Normal

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
        return self._value

    def maximum(self) -> int:
        return self._maximum

    def set_value(self, value: int) -> None:
        if value == self._value:
            return
        self._value = value
        self._update_animation()
        self.update()
        self.value_changed.emit(self._value)

    def set_maximum(self, value: int) -> None:
        if self._maximum  == value:
            return
        self._maximum = value
        self._update_animation()
        self.update()

    def state(self) -> ProgressBarState:
        """Semantic state derived from the followed track."""
        return self._state

    def set_state(self, state: ProgressBarState) -> None:
        if state == self._state:
            return
        self._state = state
        self._update_animation()
        self.update()

    def is_indeterminate(self) -> bool:
        """True while the track cannot be shown as a fraction."""
        return self._value < 0 or self._maximum < 0

    def is_animating(self) -> bool:
        """True while the indeterminate sweep timer is running."""
        return self._timer.isActive()

    def percentage(self) -> float:
        """Return the completion percentage in the ``0.0``-``100.0`` range."""
        if self._maximum is None or self._maximum == 0:
            return 0.0
        if self._value is None or self._value < 0:
            return 0.0
        return (self._value / self._maximum) * 100.0

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

    def _draw_bar(self, painter: QPainter, style: StyleDict) -> None:
        """Draw the track and the filled or sweeping chunk.

        Args:
            painter: Painter configured for this widget.
            style: Style tokens for the current state.
        """
        height = float(style.get("height", 6))
        margin = float(style.get("margin", 0))
        width = self.width() - margin * 2
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
        """Paint the track and the filled or sweeping chunk.

        The bar draws only the bar itself; descriptive text belongs to the
        owner (``AYProgressView`` draws it as a caption above the bar).

        Args:
            event: The paint event; the whole widget is repainted.
        """
        style = self._base_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity())
        self._draw_bar(painter, style)
        painter.end()

    def sizeHint(self) -> QSize:
        """Return the preferred size derived from the style height."""
        height = int(self._base_style().get("height", 6))
        return QSize(200, height)

    def minimumSizeHint(self) -> QSize:
        """Return the minimum size derived from the style height."""
        return QSize(40, self.sizeHint().height())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)


class AYProgressView(AYContainer):
    """Caption, progress bar, and percentage readout.

    Layout::

        Caption text
        [=================--------]   45%

    Args:
        parent: Parent widget.
        label: Optional caption shown above the bar.
        variant: Progress bar style variant.
        show_value: Whether the percentage readout is shown.

    Signals:
        value_changed(int): Current value of progress bar.

    """
    value_changed = Signal(int)

    def __init__(
        self,
        maximum: int = 0,
        parent: QWidget | None = None,
        label: str = "",
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
        show_value: bool = True,
    ) -> None:
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=5,
            layout_margin=0,
        )
        self._style_data = get_ayon_style().model.get_styles(
            "AYProgressBar",
            variant=variant.value,
        )
        self._show_value = show_value

        label = label or ""
        self._caption = AYLabel(label)
        self.add_widget(self._caption)
        if not label:
            self._caption.setVisible(False)

        self._row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
            layout_margin=0,
        )
        self._bar = AYProgressBar(maximum, variant=variant)
        self._value_label = AYLabel("", dim=True)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        base = self._style_data.get("base") or StyleDict()
        self._value_label.setMinimumWidth(
            base.get("value-min-width", 40)
        )

        self._row.add_widget(self._bar, stretch=1)
        self._row.add_widget(self._value_label, stretch=0)
        self.add_widget(self._row)

        self._value_label.setVisible(self._show_value)
        self._bar.value_changed.connect(self._on_progress_changed)
        self._bar.value_changed.connect(self.value_changed)
        self._on_progress_changed()

    def value(self) -> int:
        return self._bar.value()

    def set_value(self, value: int) -> None:
         self._bar.set_value(value)

    def maximum(self) -> int:
        return self._bar.maximum()

    def set_maximum(self, value: int) -> None:
        self._bar.set_maximum(value)

    def percentage(self) -> float:
        return self._bar.percentage()

    def state(self) -> ProgressBarState:
        """Semantic state derived from the followed track."""
        return self._bar.state()

    def set_state(self, state: ProgressBarState) -> None:
        self._bar.set_state(state)

    def is_indeterminate(self) -> bool:
        """True while the track cannot be shown as a fraction."""
        return self._bar.is_indeterminate()

    def is_animating(self) -> bool:
        """True while the indeterminate sweep timer is running."""
        return self._bar.is_animating()

    def set_label(self, text: str) -> None:
        """Set or replace the caption shown above the bar."""
        if not text:
            self._caption.setVisible(False)
        else:
            self._caption.setText(text)
            self._caption.setVisible(True)

    def _on_progress_changed(self) -> None:
        """Update the percentage label to match the current progress."""
        if not self._show_value or self.is_indeterminate():
            self._value_label.setText("")
            return
        self._value_label.setText(f"{self.percentage():.0f}%")
