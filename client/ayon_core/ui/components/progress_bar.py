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
from qtpy.QtWidgets importQSizePolicy, QWidget

from ..style_types import StyleDict, get_ayon_style
from ..variants import AYProgressBarVariants
from .container import AYContainer
from .label import AYLabel
from .style_mixin import StyleMixin


@dataclass
class ProgressTrack:
    """Progress of a running task, the only contract with the widget.

    The object is shared: the code that makes progress updates the values,
    the widget reads them. No callbacks or listeners are involved.

    ``value`` / ``total_value`` describe the current phase, or the whole
    task when the writer prefers a single scale. ``phase``,
    ``total_phases`` and ``phase_label`` are informational and are shown in
    the caption.

    Special states:

    * ``value < 0`` or ``total_value < 0``: indeterminate, the widget
      shows a sweeping chunk because progress cannot be expressed.
    * ``value == 0`` and ``total_value == 0``: empty, nothing started yet.

    Attributes:
        label: Overall task label.
        value: Completed steps.
        total_value: Total steps.
        failed: Whether the task failed.
        finished: Whether the task finished.
        message: Last message, or the failure reason.
        phase: Index of the current phase, starting at 1.
        total_phases: Number of phases of the task.
        phase_label: Name of the current phase.
    """

    label: str = ""
    value: int = 0
    total_value: int = 0
    failed: bool = False
    finished: bool = False
    message: str = ""
    phase: int = 1
    total_phases: int = 1
    phase_label: str = ""

    @classmethod
    def empty(cls) -> "ProgressTrack":
        """Return a track with no progress reported yet."""
        return cls()

    @property
    def is_empty(self) -> bool:
        """True while no progress was reported."""
        return self.value == 0 and self.total_value == 0

    @property
    def is_indeterminate(self) -> bool:
        """True when progress cannot be shown as a fraction."""
        return self.value < 0 or self.total_value < 0

    @property
    def percentage(self) -> float:
        """Completion in the ``0.0``-``100.0`` range."""
        if self.value < 0 or self.total_value <= 0:
            return 0.0
        fraction = self.value / self.total_value
        return max(0.0, min(fraction, 1.0)) * 100.0

    @property
    def caption(self) -> str:
        """Text that describes the current step."""
        return self.message or self.phase_label or self.label


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

    The bar is driven by a single :class:`ProgressTrack`. While visible it
    reads that object every :attr:`PROGRESS_POLL_MS`, so the writer can
    mutate the track in place or hand a new one to :meth:`set_progress`.
    No callbacks are involved, which keeps the writer free to update the
    progress any way it wants.

    Args:
        progress: Track shown by the bar.
        parent: Parent widget.
        variant: Visual style variant.

    Signals:
        progress_changed(int, int): ``(value, total_value)``; ``total_value
            == 0`` marks the bar as indeterminate.
        track_changed(object): Emitted with the track whenever the
            displayed values change.
        completed(): Emitted once when the track finishes or reaches its
            total.
    """

    progress_changed = Signal(int, int)
    track_changed = Signal(object)
    completed = Signal()

    #: How often the bound track is read while the bar is visible.
    PROGRESS_POLL_MS = 200

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
        progress: ProgressTrack | None = None,
        parent: QWidget | None = None,
        variant: AYProgressBarVariants = AYProgressBarVariants.Default,
    ) -> None:
        super().__init__(parent)
        self._variant_str = variant.value
        self._style_data = StyleDict()
        self._track = (
            progress if progress is not None else ProgressTrack.empty()
        )
        # Copy of the applied track. Comparing against a copy is what makes
        # an in-place mutation of ``_track`` detectable; comparing against
        # the track itself would always be equal.
        self._applied: ProgressTrack | None = None
        self._total: int | None = None
        self._current = 0
        self._state = ProgressBarState.Normal
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

        # Reads the track instead of being notified about changes.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.PROGRESS_POLL_MS)
        self._poll_timer.timeout.connect(self._on_poll_timeout)

        self._apply_track()

    @property
    def total(self) -> int | None:
        return self._total

    @property
    def current(self) -> int:
        return self._current

    @property
    def is_indeterminate(self) -> bool:
        """True while the track cannot be shown as a fraction."""
        if self._track.finished:
            # A finished run is complete, even when it never reported a
            # total (it stays a full bar instead of sweeping forever).
            return False
        return self._track.is_indeterminate

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

    def set_progress(self, progress: ProgressTrack) -> None:
        """Follow *progress* and show it right away.

        The bar keeps a reference to the track, so mutating that same
        object also updates the bar on the next poll. Passing a different
        object replaces the one that was followed.

        Args:
            progress: Track to show.
        """
        self._track = progress
        self._apply_track()
        self._update_polling()

    def refresh(self) -> None:
        """Re-read the followed track now.

        The poll timer calls this. Call it directly when a change has to be
        shown before the next poll.
        """
        self._apply_track()

    def reset(self) -> None:
        """Reset progress, state, and text to their initial values."""
        self._track = ProgressTrack.empty()
        self._applied = None
        self._current = 0
        self._total = None
        self._state = ProgressBarState.Normal
        self._completed = False
        self._phase = 0.0
        self._poll_timer.stop()
        self._update_animation()
        self.updateGeometry()
        self.update()
        self.progress_changed.emit(self._current, 0)

    def _on_poll_timeout(self) -> None:
        """Re-read the followed track."""
        self._apply_track()

    def _apply_track(self) -> None:
        """Copy the track onto the widget state and repaint when it changed."""
        track = self._track
        if self._applied is not None and track == self._applied:
            return
        # Snapshot the values: comparing against a copy is what detects an
        # in-place mutation of the same object on the next poll.
        self._applied = replace(track)

        if track.finished:
            # A finished run is complete; ignore a value that was left
            # short of the total.
            self._total = max(track.total_value, 1)
            self._current = self._total
        elif track.is_indeterminate or track.is_empty:
            self._total = None
            self._current = 0
        else:
            self._total = track.total_value
            self._current = max(0, min(track.value, track.total_value))

        if track.failed:
            self._state = ProgressBarState.Error
        elif track.finished:
            self._state = ProgressBarState.Success
        else:
            self._state = ProgressBarState.Normal

        self._update_animation()
        self.update()
        self.progress_changed.emit(self._current, self._total or 0)
        self._emit_completed_if_done()
        self.track_changed.emit(track)

    def _update_polling(self) -> None:
        """Poll only while visible and while there is something to read."""
        track = self._track
        done = track.finished or track.failed
        if self.isVisible() and not done:
            if not self._poll_timer.isActive():
                self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _emit_completed_if_done(self) -> None:
        """Emit ``completed`` once per run when the track is done."""
        if self._completed:
            return
        if self._track.finished:
            self._completed = True
            self.completed.emit()
            return
        if self._total is None or self._total <= 0:
            return
        if self._current >= self._total:
            self._completed = True
            self.completed.emit()

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
        # Pick up anything that changed while hidden, then keep reading.
        self._apply_track()
        self._update_polling()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        self._poll_timer.stop()
        super().hideEvent(event)


class AYProgressView(AYContainer):
    """Caption, progress bar, and percentage readout.

    Layout::

        Caption text
        [=================--------]   45%

    The bar and the caption are driven by a single :class:`ProgressTrack`,
    the same object the writer updates, so no callbacks are involved.

    Args:
        parent: Parent widget.
        label: Optional caption shown above the bar.
        progress: Track to show.
        variant: Progress bar style variant.
        show_value: Whether the percentage readout is shown.

    Signals:
        progress_changed(int, int): Re-emitted from the inner bar.
        completed(): Emitted once when the track finishes or reaches its
            total.
    """

    progress_changed = Signal(int, int)
    completed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        progress: ProgressTrack | None = None,
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
        self._initial_label = str(label or "")

        self._caption: AYLabel | None = None
        if label:
            self._caption = AYLabel(label)
            self.add_widget(self._caption)

        self._row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
            layout_margin=0,
        )
        self._bar = AYProgressBar(progress=progress, variant=variant)
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
        self._bar.completed.connect(self.completed.emit)
        self._bar.track_changed.connect(self._on_track_changed)
        self._on_progress_changed()

        self._progress: ProgressTrack | None = progress
        # The view keeps reading the track while it is bound, also while
        # hidden: the owner shows it as soon as real progress arrives.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(AYProgressBar.PROGRESS_POLL_MS)
        self._poll_timer.timeout.connect(self._bar.refresh)

    def bind(self, progress: ProgressTrack) -> None:
        """Drive this view from *progress*.

        The view is reset first so a reused view cannot briefly show the
        previous run's value, colour, or caption.

        Args:
            progress: Track to follow. The bar keeps a reference to it, so
                mutating that object updates the view on the next poll.
        """
        self.unbind()
        self.reset()
        self._progress = progress
        self._bar.set_progress(progress)
        if not (progress.finished or progress.failed):
            self._poll_timer.start()

    def unbind(self) -> None:
        """Stop following the bound track, if any."""
        self._poll_timer.stop()
        self._progress = None
        self._bar.reset()

    def _on_track_changed(self, track: ProgressTrack) -> None:
        """Update the caption from the track the bar applied."""
        if track.caption:
            self.set_label(track.caption)
        if track.finished or track.failed:
            self._poll_timer.stop()

    # --- private

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

    def reset(self) -> None:
        """Reset the bar, the caption, and the percentage readout.

        The caption falls back to the label the view was created with.
        """
        if self._caption is not None:
            self._caption.setText(self._initial_label)
        self._bar.reset()
        self._value_label.setText("")
