"""Determinate and indeterminate progress bar drawn in the AYON style."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from qtpy.QtCore import QRectF, QSize, Qt, QTimer, Signal
from qtpy.QtGui import (
    QCloseEvent,
    QColor,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from qtpy.QtWidgets import QDialog, QSizePolicy, QWidget

from ..style_types import StyleDict, get_ayon_style
from ..variants import AYProgressBarVariants
from .buttons import AYButton
from .container import AYContainer
from .label import AYLabel
from .layouts import AYVBoxLayout
from .style_mixin import StyleMixin

if TYPE_CHECKING:
    from ...lib.progress import ProgressReporter, ProgressState


class ProgressBarState(Enum):
    """Semantic state controlling the colour of the filled chunk."""

    Normal = "normal"
    Error = "error"
    Warning = "warning"
    Success = "success"


class AYProgressBar(StyleMixin, QWidget):
    """Determinate and indeterminate progress bar in the AYON style.

    Every visual property (height, radius, colours, sweep ratio, ...) is
    read from the ``AYProgressBar`` block of ``ayon_style.json``.  The
    native Qt style is still routed through :class:`AYONStyle`
    (``setStyle``) so the widget inherits the AYON font and palette, but
    the painting itself happens in :meth:`paintEvent`, independent of any
    stylesheet or ``QStyle`` drawing code.

    Args:
        parent: Parent widget.
        variant: Visual style variant.
        total: Total number of steps. ``None`` or ``0`` makes the bar
            indeterminate and animates a sweeping chunk instead.

    Signals:
        progress_changed(int, int): ``(completed, total)``; ``total == 0``
            marks the bar as indeterminate.
        completed(): Emitted once when a determinate bar reaches its total.
    """

    progress_changed = Signal(int, int)
    completed = Signal()

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
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
        total: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._variant_str = variant.value
        self._style_data = StyleDict()
        self._total = total
        self._current = 0
        self._state = ProgressBarState.Normal
        self._text = ""
        self._text_visible = True
        self._completed = False
        self._phase = 0.0

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
        self._timer.timeout.connect(self._advance_phase)

    @property
    def total(self) -> int | None:
        return self._total

    @property
    def current(self) -> int:
        return self._current

    @property
    def is_indeterminate(self) -> bool:
        return self.total is None or self.total == 0

    @property
    def is_animating(self) -> bool:
        """True while the indeterminate sweep timer is running."""
        return self._timer.isActive()

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

    def _advance_phase(self) -> None:
        """Advance the indeterminate sweep phase and repaint."""
        step = self._timer.interval() / self._SWEEP_DURATION_MS
        self._phase = (self._phase + step) % 1.0
        self.update()

    def _update_animation(self) -> None:
        """Start the sweep timer while indeterminate and visible."""
        if self.is_indeterminate and self.isVisible():
            if not self._timer.isActive():
                self._phase = 0.0
                self._timer.start()
        else:
            self._timer.stop()

    def set_total(self, total: int | None) -> None:
        """Set the total number of steps.

        Args:
            total: Number of steps, or ``None`` for indeterminate.
        """
        self._total = total
        self._completed = False
        if total is not None and self._current > max(total, 0):
            self._current = max(total, 0)
        self._update_animation()
        self.update()
        self.progress_changed.emit(self._current, self._total or 0)
        self._emit_completed_if_done()

    def set_progress(self, value: int, total: int | None = None) -> None:
        """Set the current progress value.

        Args:
            value: Current number of completed steps.
            total: Optional total to set before applying *value*.
        """
        if total is not None and total != self._total:
            self._total = total
            self._completed = False
            self._update_animation()
        if self._total is None:
            self._current = value
        else:
            self._current = max(0, min(value, self._total))
        self.update()
        self.progress_changed.emit(self._current, self._total or 0)
        self._emit_completed_if_done()

    def set_indeterminate(self) -> None:
        """Switch to indeterminate mode (sweeping chunk, no total)."""
        self.set_total(None)

    def set_state(self, state: ProgressBarState) -> None:
        """Set the semantic state that colours the chunk."""
        if state is self._state:
            return
        self._state = state
        self.update()

    def reset(self) -> None:
        """Reset progress, state, and text to their initial values."""
        self._current = 0
        self._total = None
        self._state = ProgressBarState.Normal
        self._text = ""
        self._text_visible = True
        self._completed = False
        self._phase = 0.0
        self._update_animation()
        self.update()
        self.progress_changed.emit(self._current, 0)

    def _emit_completed_if_done(self) -> None:
        """Emit ``completed`` once per run when the total is reached."""
        if self._completed:
            return
        if self._total is None or self._total <= 0:
            return
        if self._current >= self._total:
            self._completed = True
            self.completed.emit()

    def set_text(self, text: str) -> None:
        """Set the text drawn over the bar."""
        if text == self._text:
            return
        self._text = text
        self.update()

    def set_text_visible(self, visible: bool) -> None:
        """Show or hide the text drawn over the bar."""
        visible = bool(visible)
        if visible == self._text_visible:
            return
        self._text_visible = visible
        self.update()

    def percentage(self) -> float:
        """Return the completion percentage in the ``0.0``-``100.0`` range."""
        if self.total is None or self.total == 0:
            return 0.0
        return (self.current / self.total) * 100.0

    # --- painting
    def _chunk_color(self, style: StyleDict) -> QColor:
        """Return the chunk colour for the current semantic state."""
        key = self._STATE_COLOR_KEY.get(self._state, "chunk-color")
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

        if self.is_indeterminate:
            chunk_w = width * float(style.get("sweep-ratio", 0.3))
            x = track.x() - chunk_w + self._phase * (width + chunk_w)
            chunk = QRectF(x, top, chunk_w, height)
            painter.save()
            painter.setClipRect(track)
            painter.setBrush(self._chunk_color(style))
            painter.drawRoundedRect(chunk, radius, radius)
            painter.restore()
        elif self._current > 0:
            chunk_w = width * (self.percentage() / 100.0)
            chunk = QRectF(track.x(), top, chunk_w, height)
            painter.setBrush(self._chunk_color(style))
            painter.drawRoundedRect(chunk, radius, radius)

    def _draw_text(self, painter: QPainter, style: StyleDict) -> None:
        """Draw the descriptive text centred over the bar."""
        margin = int(style.get("text-margin", 6))
        painter.setPen(QColor(style.get("text-color", "#f4f5f5")))
        painter.setFont(self.font())
        rect = self.rect().adjusted(margin, 0, -margin, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the track, chunk, and optional text.

        Args:
            event: The paint event; the whole widget is repainted.
        """
        style = self._base_style()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity())
        self._draw_bar(painter, style)
        if self._text_visible and self._text:
            self._draw_text(painter, style)
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
        total: Total number of steps; ``None`` for indeterminate.
        variant: Progress bar style variant.
        show_value: Whether the percentage readout is shown.

    Signals:
        progress_changed(int, int): Re-emitted from the inner bar.
        completed(): Emitted once when the bound reporter finishes, or
            when the inner bar completes if no reporter is bound.
    """

    progress_changed = Signal(int, int)
    progress_ping = Signal(object)
    completed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        total: int | None = None,
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
        self._show_value = bool(show_value)

        self._caption: AYLabel | None = None
        if label:
            self._caption = AYLabel(label)
            self.add_widget(self._caption)

        self._row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
            layout_margin=0,
        )
        self._bar = AYProgressBar(variant=variant, total=total)
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
        self._bar.progress_changed.connect(self._on_progress_changed)
        self._bar.progress_changed.connect(self.progress_changed.emit)
        self._bar.completed.connect(self._on_bar_completed)

        self._reporter: ProgressReporter | None = None
        self._reporter_completed = False
        # Reporter callbacks can arrive on a worker thread; hop to the Qt
        # thread before touching any widget.
        self.progress_ping.connect(
            self._apply, Qt.ConnectionType.QueuedConnection
        )

    def bind(self, reporter: ProgressReporter) -> None:
        """Drive this view from *reporter*.

        Args:
            reporter: The progress source to follow.
        """
        self.unbind()
        self._reporter = reporter
        self._reporter_completed = False
        reporter.add_listener(self._on_state)

    def unbind(self) -> None:
        """Stop following the bound reporter, if any."""
        if self._reporter is not None:
            self._reporter.remove_listener(self._on_state)
            self._reporter = None

    def _on_state(self, state: ProgressState) -> None:
        """Queue a reporter snapshot for the Qt thread."""
        self.progress_ping.emit(state)

    def _apply(self, state: ProgressState) -> None:
        """Mirror a reporter snapshot onto the bar."""
        if state.total != self._bar.total:
            self._bar.set_total(state.total)
        self._bar.set_progress(state.completed)
        caption = state.message or state.phase or state.label
        if caption:
            self.set_label(caption)
        if state.failed:
            self.set_state(ProgressBarState.Error)
        elif state.finished:
            self.set_state(ProgressBarState.Success)
            if not self._reporter_completed:
                self._reporter_completed = True
                self.completed.emit()
        else:
            self.set_state(ProgressBarState.Normal)

    # --- private
    def _on_bar_completed(self) -> None:
        """Forward bar completion only when no reporter is bound."""
        if self._reporter is None:
            self.completed.emit()

    def _on_progress_changed(self) -> None:
        """Update the percentage label to match the current progress."""
        if not self._show_value or self._bar.is_indeterminate:
            self._value_label.setText("")
            return
        self._value_label.setText(f"{self._bar.percentage():.0f}%")

    # --- public API
    @property
    def progress_bar(self) -> AYProgressBar:
        """Return the inner :class:`AYProgressBar`."""
        return self._bar

    @property
    def value_label(self) -> AYLabel:
        """Return the percentage readout label."""
        return self._value_label

    def set_label(self, text: str) -> None:
        """Set or replace the caption shown above the bar."""
        if self._caption is None:
            if not text:
                return
            self._caption = AYLabel(text)
            self.insert_widget(0, self._caption)
            return
        self._caption.setText(text)

    def set_total(self, total: int | None) -> None:
        """Set the total number of steps (``None`` for indeterminate)."""
        self._bar.set_total(total)

    def set_progress(self, value: int, total: int | None = None) -> None:
        """Set the current progress value."""
        self._bar.set_progress(value, total)

    def set_state(self, state: ProgressBarState) -> None:
        """Set the semantic state that colours the chunk."""
        self._bar.set_state(state)

    def set_text(self, text: str) -> None:
        """Set the text drawn over the bar."""
        self._bar.set_text(text)

    def reset(self) -> None:
        """Reset the bar and clear the percentage readout."""
        self._reporter_completed = False
        self._bar.reset()
        self._value_label.setText("")


class AYProgressDialog(QDialog):
    """Modal dialog wrapping :class:`AYProgressView`.

    Args:
        parent: Parent widget.
        label: Message shown above the bar and used as the window title.
        total: Total number of steps; ``None`` for indeterminate.
        variant: Progress bar style variant.
        cancel_text: Text of the cancel button.
        cancellable: Whether a cancel button is offered.
        close_on_complete: Close the dialog once the bar completes.

    Signals:
        canceled(): Emitted when the user cancels or closes the dialog
            before it finished.
    """

    canceled = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        total: int | None = None,
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
        cancel_text: str = "Cancel",
        cancellable: bool = True,
        close_on_complete: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setStyle(get_ayon_style())
        self.setWindowTitle(label or "Progress")
        self.setModal(True)
        self.setContentsMargins(0, 0, 0, 0)

        self._finished = False
        self._close_on_complete = bool(close_on_complete)

        root = AYVBoxLayout(self, margin=0, spacing=0)

        body = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )
        self._view = AYProgressView(
            label=label,
            total=total,
            variant=variant,
        )
        body.add_widget(self._view)

        self._cancel_button: AYButton | None = None
        if cancellable:
            row = AYContainer(
                layout=AYContainer.Layout.HBox,
                layout_spacing=8,
                layout_margin=0,
            )
            row.addStretch(1)
            self._cancel_button = AYButton(cancel_text)
            self._cancel_button.clicked.connect(self._on_cancel_clicked)
            row.add_widget(self._cancel_button)
            body.add_widget(row)

        root.addWidget(body)
        self._view.completed.connect(self._on_completed)

    # --- public API
    @property
    def progress_bar(self) -> AYProgressBar:
        """Return the inner :class:`AYProgressBar`."""
        return self._view.progress_bar

    @property
    def progress_view(self) -> AYProgressView:
        """Return the :class:`AYProgressView` holding the bar."""
        return self._view

    @property
    def cancel_button(self) -> AYButton | None:
        """Return the cancel button, or ``None`` when not cancellable."""
        return self._cancel_button

    def set_label(self, text: str) -> None:
        """Set the message shown above the bar."""
        if text:
            self.setWindowTitle(text)
        self._view.set_label(text)

    def set_total(self, total: int | None) -> None:
        """Set the total number of steps (``None`` for indeterminate)."""
        self._view.set_total(total)

    def set_progress(self, value: int, total: int | None = None) -> None:
        """Set the current progress value."""
        self._view.set_progress(value, total)

    def set_state(self, state: ProgressBarState) -> None:
        """Set the semantic state that colours the chunk."""
        self._view.set_state(state)

    def finish(self) -> None:
        """Close the dialog without reporting a cancellation."""
        self._finished = True
        if self._cancel_button is not None:
            self._cancel_button.setEnabled(False)
        self.accept()

    # --- private
    def _on_completed(self) -> None:
        self._finished = True
        if self._cancel_button is not None:
            self._cancel_button.setEnabled(False)
        if self._close_on_complete:
            self.accept()

    def _on_cancel_clicked(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.canceled.emit()
        self.reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._finished:
            self._finished = True
            self.canceled.emit()
        super().closeEvent(event)
