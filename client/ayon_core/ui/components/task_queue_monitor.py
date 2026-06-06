from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass
from typing import Any

from qtpy.QtCore import (
    QEvent,
    QRectF,
    Qt,
    QTimer,
    Slot,  # type: ignore
)
from qtpy.QtGui import QCloseEvent, QColor, QPainter, QPainterPath, QPen
from qtpy.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..style import get_ayon_style_data
from .style_mixin import StyleMixin
from .task_queue import AsyncTaskQueue

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress widget
# ---------------------------------------------------------------------------

#: Milliseconds to wait after the last state change before repainting.
_DEBOUNCE_MS: int = 50
#: Pulse animation frame interval in milliseconds.
_PULSE_INTERVAL_MS: int = 250
#: Seconds after queue_empty before finished segments are cleared.
_CLEAR_DELAY_MS: int = 200


class _TaskStatus(enum.Enum):
    """Lifecycle states tracked by the progress widget."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class _TrackedTask:
    """Internal snapshot of a task observed by the progress widget.

    Attributes:
        name: Task name as reported by the queue signals.
        priority: Numeric priority value from :class:`AsyncTask`.
        status: Current lifecycle status.
    """

    name: str
    priority: int
    status: _TaskStatus = _TaskStatus.PENDING


def _priority_bucket(priority: int) -> str:
    """Map a numeric priority to a colour bucket name.

    Args:
        priority: Numeric priority from :class:`AsyncTask`.

    Returns:
        One of ``"high"``, ``"medium"``, or ``"low"``.
    """
    if priority <= 1:
        return "high"
    if priority <= 9:
        return "medium"
    return "low"


class AsyncTaskQueueMonitor(StyleMixin, QWidget):
    """Compact segmented progress bar that mirrors an :class:`AsyncTaskQueue`.

    Each task observed from the queue is rendered as a color-coded segment.
    Segment colors map to priority: high (orange), medium (green), low
    (blue).  The currently running task pulses to indicate activity.

    The widget has a fixed maximum height of 24 px and expands horizontally
    to fill its container.

    A rich tooltip (shown on hover) reports totals by status, a percentage
    breakdown per priority bucket, and the name of the currently active task.

    Redraws are debounced so that bursts of rapid task completions do not
    cause excessive paint events.

    Args:
        task_queue: The :class:`AsyncTaskQueue` instance to observe.
        update_interval_ms: Debounce interval in milliseconds between
            successive redraws (default 50 ms).
        parent: Optional parent :class:`QWidget`.

    Example:
        ::

            queue = get_task_queue()
            bar = AsyncTaskQueueMonitor(queue)
            layout.addWidget(bar)
    """

    #: Fixed maximum height in pixels.
    MAX_HEIGHT: int = 10

    def __init__(
        self,
        task_queue: AsyncTaskQueue,
        update_interval_ms: int = _DEBOUNCE_MS,
        parent: Any = None,
    ) -> None:
        """Initialise and connect to *task_queue* signals.

        Args:
            task_queue: Queue instance to observe.
            update_interval_ms: Debounce redraw interval in ms.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._queue: AsyncTaskQueue = task_queue
        self._tasks: list[_TrackedTask] = []
        self._pulse_phase: float = 0.0

        # Load style configuration from AYON style system
        style_data = get_ayon_style_data("AsyncTaskQueueMonitor") or {}
        style_data.set_context(self)
        if not style_data:
            log.warning(
                "AsyncTaskQueueMonitor: Style data not available, using defaults"
            )

        # Colors
        self._bg_color = QColor(style_data.get("background-color", "#1c2026"))
        self._bg_outline_color = QColor(
            style_data.get("outline-color", "#3F4552")
        )
        self._priority_colors = {
            "high": QColor(style_data.get("high-priority-color", "#E87D0D")),
            "medium": QColor(
                style_data.get("medium-priority-color", "#4CAF50")
            ),
            "low": QColor(style_data.get("low-priority-color", "#2196F3")),
        }
        self._failed_color = QColor(style_data.get("failed-color", "#F44336"))

        # Alphas (opacity values)
        self._completed_alpha = style_data.get("completed-alpha", 0.45)
        self._pending_alpha = style_data.get("pending-alpha", 0.70)

        # Dimensions
        self._segment_gap = style_data.get("segment-gap", 2)
        self._bar_radius = style_data.get("bar-radius", 3)

        # Debounce timer — single-shot, restarted on every state change.
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(update_interval_ms)
        self._update_timer.timeout.connect(self._on_debounced_update)

        # Pulse animation timer.
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(_PULSE_INTERVAL_MS)
        self._pulse_timer.timeout.connect(self._advance_pulse)

        # Clear timer.
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._clear_finished)

        # Connect queue signals.
        task_queue.task_enqueued.connect(self._on_task_enqueued)
        task_queue.task_started.connect(self._on_task_started)
        task_queue.task_completed.connect(self._on_task_completed)
        task_queue.task_failed.connect(self._on_task_failed)
        task_queue.task_cancelled.connect(self._on_task_cancelled)
        task_queue.queue_empty.connect(self._on_queue_empty)

        # Widget appearance.
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.setMinimumHeight(self.MAX_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    @Slot(str, int)
    def _on_task_enqueued(self, name: str, priority: int) -> None:
        """Record a newly enqueued task.

        Args:
            name: Task name.
            priority: Numeric priority.
        """
        self._tasks.append(_TrackedTask(name, priority, _TaskStatus.PENDING))
        self._schedule_update()

    @Slot(str)
    def _on_task_started(self, name: str) -> None:
        """Transition the first matching pending task to running.

        Args:
            name: Task name.
        """
        has_running = False
        for task in reversed(self._tasks):
            if task.name == name and task.status == _TaskStatus.PENDING:
                task.status = _TaskStatus.RUNNING
                has_running = True
                break
        if has_running and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        self._schedule_update()

    @Slot(str, object)
    def _on_task_completed(self, name: str, _result: object) -> None:
        """Mark the first matching active task as completed.

        Args:
            name: Task name.
            _result: Unused task result.
        """
        self._transition(name, _TaskStatus.COMPLETED)

    @Slot(str, str)
    def _on_task_failed(self, name: str, _error: str) -> None:
        """Mark the first matching active task as failed.

        Args:
            name: Task name.
            _error: Unused error message.
        """
        self._transition(name, _TaskStatus.FAILED)

    @Slot(str, str)
    def _on_task_cancelled(self, name: str, _ctx: str) -> None:
        """Mark the first matching active task as cancelled.

        Args:
            name: Task name.
            _ctx: Unused context id.
        """
        self._transition(name, _TaskStatus.CANCELLED)

    @Slot()
    def _on_queue_empty(self) -> None:
        """Schedule removal of finished segments after a short delay."""
        self._schedule_clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, name: str, status: _TaskStatus) -> None:
        """Move the first active (pending/running) task with *name* to *status*.

        Args:
            name: Task name to look up.
            status: Target status.
        """
        active = (_TaskStatus.PENDING, _TaskStatus.RUNNING)
        for task in reversed(self._tasks):
            if task.name == name and task.status in active:
                task.status = status
                break
        self._schedule_update()

        # If no active tasks remain, schedule cleanup so completed
        # segments don't linger after pool tasks finish.
        if self._tasks and not any(t.status in active for t in self._tasks):
            self._schedule_clear()

    def _schedule_update(self) -> None:
        """Restart the debounce timer to coalesce rapid state changes."""
        self._update_timer.start()

    def _schedule_clear(self) -> None:
        # ensure clear is never earlier than pending debounced paint cadence
        delay = max(_CLEAR_DELAY_MS, self._update_timer.interval())
        self._clear_timer.start(delay)

    def _on_debounced_update(self) -> None:
        """Slot called by the debounce timer; triggers a repaint and tooltip."""
        self.update()

    def _advance_pulse(self) -> None:
        """Advance the pulse phase and repaint if any task is running."""
        self._pulse_phase = (self._pulse_phase + 0.06) % 1.0
        has_running = any(t.status == _TaskStatus.RUNNING for t in self._tasks)
        if has_running:
            self.update()
        else:
            self._pulse_timer.stop()

    def _clear_finished(self) -> None:
        """Remove all terminal-state tasks, keeping only active ones."""
        # don't clear before pending debounced repaint runs
        if self._update_timer.isActive():
            self._clear_timer.start(self._update_timer.remainingTime() + 1)
            return

        terminal = (
            _TaskStatus.COMPLETED,
            _TaskStatus.FAILED,
            _TaskStatus.CANCELLED,
        )
        self._tasks = [t for t in self._tasks if t.status not in terminal]
        self.update()

    def _active_task_name(self) -> str:
        """Return the name of the first running task, or an empty string."""
        for task in self._tasks:
            if task.status == _TaskStatus.RUNNING:
                return task.name
        return ""

    def _build_tooltip(self) -> str:
        """Compose the hover tooltip text from current task state.

        Returns:
            A multi-line string describing queue status, priority breakdown,
            and the currently active task name.
        """
        total = len(self._tasks)
        if total == 0:
            return "No tasks"

        by_status: dict[_TaskStatus, int] = {s: 0 for s in _TaskStatus}
        by_bucket: dict[str, int] = {"high": 0, "medium": 0, "low": 0}

        for t in self._tasks:
            by_status[t.status] += 1
            by_bucket[_priority_bucket(t.priority)] += 1

        lines: list[str] = [
            f"<b>Tasks: {total}</b>",
            (
                f"Pending: {by_status[_TaskStatus.PENDING]}  "
                f"Running: {by_status[_TaskStatus.RUNNING]}  "
                f"Completed: {by_status[_TaskStatus.COMPLETED]}  "
                f"Failed: {by_status[_TaskStatus.FAILED]}"
            ),
        ]

        # Priority breakdown percentages.
        bucket_parts: list[str] = []
        for bucket, label in (
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ):
            count = by_bucket[bucket]
            if count:
                pct = round(100 * count / total)
                bucket_parts.append(f"{label}: {pct}%")
        if bucket_parts:
            lines.append("Priority — " + "  ".join(bucket_parts))

        active = self._active_task_name()
        if active:
            lines.append(f"Active: <i>{active}</i>")

        return "<br>".join(lines)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def event(self, event: QEvent) -> bool:
        """Handle tooltip requests to provide dynamic hover content.

        Args:
            event: Incoming Qt event.

        Returns:
            Forwarded return value from the base implementation.
        """
        if event.type() == QEvent.Type.Enter:
            QToolTip.showText(
                event.globalPos(),  # type: ignore
                self._build_tooltip(),
                self,
                self.rect(),
            )
            return True
        return super().event(event)

    def paintEvent(self, _event: Any) -> None:
        """Render the segmented progress bar.

        Segments are drawn left-to-right in enqueue order.  Completed and
        cancelled segments are dimmed; failed segments are drawn in red;
        the running segment pulses.

        Args:
            _event: Unused paint event.
        """
        tasks = self._tasks

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.save()
        painter.setBrush(self._bg_color)
        painter.setPen(QPen(self._bg_outline_color, 1))
        painter.drawRoundedRect(
            self.rect(), self._bar_radius, self._bar_radius
        )  # Background
        painter.restore()

        if not tasks:
            return

        margin = 3
        width = self.width() - 2 * margin
        height = self.height() - 2 * margin

        n = len(tasks)
        total_gap = self._segment_gap * (n - 1)
        seg_w = max(1.0, (width - total_gap) / n)
        h = float(height)

        for i, task in enumerate(tasks):
            x = i * (seg_w + self._segment_gap)

            # Determine base colour.
            if task.status == _TaskStatus.FAILED:
                base_color = QColor(self._failed_color)
            else:
                base_color = QColor(
                    self._priority_colors[_priority_bucket(task.priority)]
                )

            # Apply alpha based on status.
            if task.status in (
                _TaskStatus.COMPLETED,
                _TaskStatus.CANCELLED,
            ):
                base_color.setAlphaF(self._completed_alpha)
            elif task.status == _TaskStatus.RUNNING:
                pulse = 0.65 + 0.35 * math.sin(self._pulse_phase * 2 * math.pi)
                base_color.setAlphaF(pulse)
            else:
                base_color.setAlphaF(self._pending_alpha)

            painter.setBrush(base_color)
            painter.setPen(Qt.PenStyle.NoPen)

            path = QPainterPath()
            path.addRoundedRect(
                QRectF(x + margin, margin, seg_w, h),
                self._bar_radius,
                self._bar_radius,
            )
            painter.drawPath(path)

        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Clean up signal connections on widget destruction."""
        self._queue.task_enqueued.disconnect(self._on_task_enqueued)
        self._queue.task_started.disconnect(self._on_task_started)
        self._queue.task_completed.disconnect(self._on_task_completed)
        self._queue.task_failed.disconnect(self._on_task_failed)
        self._queue.task_cancelled.disconnect(self._on_task_cancelled)
        self._queue.queue_empty.disconnect(self._on_queue_empty)
        super().closeEvent(event)
