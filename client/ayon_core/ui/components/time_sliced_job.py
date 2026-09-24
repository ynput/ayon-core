"""Run long UI-thread work in small time slices.

Some work must happen on the UI thread, e.g. creating many items of a Qt
model. Doing it in one go blocks the event loop, so animations (like
'AYSkeletonLoader') freeze and the UI does not respond.

'TimeSlicedJob' runs a generator step by step and returns control to the
event loop whenever a time budget is spent. It relies only on 'QTimer',
so it works in any running Qt event loop, including DCCs.

Example:
    def _build_items(self):
        for data in self._data:
            self._items.append(create_item(data))
            yield

    job = TimeSlicedJob(self._build_items(), parent=self)
    job.finished.connect(self._on_items_built)
    job.start()
"""

from __future__ import annotations

import logging
import time
from typing import Generator, Optional

from qtpy.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)


class TimeSlicedJob(QObject):
    """Run a generator on the UI thread in time slices.

    The generator should 'yield' often (e.g. after each created item).
    The job keeps calling it until ``budget_ms`` is spent, then lets the
    event loop process other events before it continues.

    Args:
        generator: Generator doing the work.
        budget_ms: Time in milliseconds a single slice may take.
        parent: Parent object.
    """

    #: Emitted when the generator is exhausted or failed. Not emitted
    #:   if cancelled, so a failure never leaves a caller waiting forever.
    finished = Signal()

    def __init__(
        self,
        generator: Generator,
        budget_ms: int = 10,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._generator = generator
        self._budget = budget_ms / 1000.0
        self._running = False

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(self._run_slice)
        self._timer = timer

    def is_running(self) -> bool:
        """Job was started and did not finish or was not cancelled yet.

        Returns:
            bool: Job is running.
        """
        return self._running

    def start(self) -> None:
        """Start the job, the first slice runs from the event loop."""
        if self._running:
            return
        self._running = True
        self._timer.start()

    def cancel(self) -> None:
        """Stop the job, 'finished' is not emitted."""
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self._generator.close()

    def _run_slice(self) -> None:
        if not self._running:
            return
        end = time.perf_counter() + self._budget
        try:
            while time.perf_counter() < end:
                next(self._generator)
        except StopIteration:
            pass
        except Exception:
            log.warning("Time sliced job failed", exc_info=True)
        else:
            self._timer.start()
            return
        self._running = False
        self.finished.emit()
