"""Thread-safe, UI-agnostic progress reporting.

The reporter holds an immutable :class:`ProgressState` snapshot and fans
it out to listeners.  Listeners are always invoked **outside** the
internal lock, so a callback may safely call back into the reporter.
Delivery is serialised, so a listener never observes an older snapshot
after a newer one.

Updates are coalesced to at most one notification per ``min_interval``
seconds.  Because coalescing drops intermediate states, ``finish()``,
``fail()``, and :meth:`ProgressReporter.flush` bypass it so terminal
state is never lost.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProgressState:
    """Immutable snapshot handed to listeners.

    Attributes:
        label: Overall task label.
        phase: Name of the phase currently running.
        completed: Steps completed in the current phase.
        total: Total steps of the current phase; ``None`` or ``0`` when
            the phase is indeterminate.
        failed: Whether the run failed.
        message: Last message, or the failure reason.
        finished: Whether the run finished.
        weight: Relative weight of the current phase.
        overall: Weighted progress across all declared phases, from
            ``0.0`` to ``1.0``.  ``None`` until a phase has been declared
            through :meth:`ProgressReporter.set_phases` or
            :meth:`ProgressReporter.set_phase`.
    """

    label: str = ""
    phase: str = ""
    completed: int = 0
    total: int | None = None
    failed: bool = False
    message: str = ""
    finished: bool = False
    weight: float = 1.0
    overall: float | None = None


class ProgressReporter:
    """Thread-safe, UI-agnostic progress source.

    Args:
        label: Initial task label.
        total: Initial total for the first phase.
        min_interval: Minimum number of seconds between notifications.
    """

    def __init__(
        self,
        label: str = "",
        total: int | None = None,
        min_interval: float = 0.05,
    ) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Callable[[ProgressState], None]] = []
        self._min_interval = max(0.0, float(min_interval))
        self._last_update = 0.0
        self._phases: dict[str, float] = {}
        self._phase_progress: dict[str, float] = {}
        # Serialises capture+delivery so a thread that read an older
        # snapshot can never deliver it after a newer one.  Reentrant
        # because a listener is allowed to call back into the reporter.
        self._publish_lock = threading.RLock()
        self._state = ProgressState(label=label, total=total)

    # --- describing the run
    def set_label(self, label: str) -> None:
        """Set the overall task label.

        Args:
            label: New label.
        """
        self._mutate(label=label)

    def set_message(self, message: str) -> None:
        """Set the message describing the current step.

        Args:
            message: New message.
        """
        self._mutate(message=message)

    def set_phases(
        self,
        phases: Iterable[str | tuple[str, float]] | Mapping[str, float],
    ) -> None:
        """Declare the phase plan used to compute overall progress.

        Declaring the plan up front is what makes ``overall`` meaningful:
        without it the denominator only contains the phases seen so far.

        Args:
            phases: A mapping of phase name to weight, an iterable of
                ``(name, weight)`` pairs, or an iterable of names (each
                weighted ``1.0``).
        """
        with self._lock:
            for name, weight in self._iter_phases(phases):
                self._phases.setdefault(name, max(0.0, float(weight)))
                self._phase_progress.setdefault(name, 0.0)
            self._state = self._with_overall(self._state)
        self._publish()

    def set_phase(self, phase: str, weight: float = 1.0) -> None:
        """Switch to *phase*, resetting the phase counters.

        Args:
            phase: Phase name, e.g. ``"UPLOAD"``.
            weight: Relative weight in the overall progress.  Applied the
                first time the phase is announced.
        """
        with self._lock:
            if phase not in self._phases:
                self._phases[phase] = max(0.0, float(weight))
            self._phase_progress.setdefault(phase, 0.0)
            self._state = self._with_overall(
                replace(self._state, phase=phase, completed=0, total=None)
            )
        self._publish()

    def set_total(self, total: int | None) -> None:
        """Set the total number of steps for the current phase.

        Args:
            total: Total steps, or ``None`` for indeterminate.
        """
        self._mutate(total=total)

    # --- reporting (safe from any thread)
    def step(self, amount: int = 1) -> None:
        """Advance the current phase by *amount* steps.

        Counting works with or without a total, so an indeterminate run
        is still observable.  When a total is known the count is clamped
        to it, so a runaway loop cannot overshoot.

        Args:
            amount: Number of steps to add.
        """
        with self._lock:
            completed = self._state.completed + amount
            total = self._state.total
            if total is not None:
                completed = min(completed, total)
            self._state = self._with_overall(
                replace(self._state, completed=completed)
            )
        self._publish()

    def set_progress(self, completed: int) -> None:
        """Set the completed step count of the current phase.

        Args:
            completed: Number of completed steps.
        """
        with self._lock:
            self._state = self._with_overall(
                replace(self._state, completed=completed)
            )
        self._publish()

    def finish(self) -> None:
        """Mark the run as finished and complete the current phase.

        Idempotent: once the run has finished or failed, further calls
        are ignored so listeners are not notified a second time.
        """
        with self._lock:
            if self._state.finished or self._state.failed:
                return
            if self._state.phase:
                self._phase_progress[self._state.phase] = 1.0
            state = self._state
            if state.total:
                state = replace(state, completed=state.total)
            self._state = self._with_overall(
                replace(state, finished=True)
            )
        self._publish(force=True)

    def fail(self, message: str = "") -> None:
        """Mark the run as failed.

        Args:
            message: Failure reason; ignored when empty.
        """
        with self._lock:
            if self._state.finished or self._state.failed:
                return
            self._state = self._with_overall(
                replace(
                    self._state,
                    failed=True,
                    message=message or self._state.message,
                )
            )
        self._publish(force=True)

    # --- observation
    def add_listener(
        self,
        callback: Callable[[ProgressState], None],
        emit_immediately: bool = True,
    ) -> None:
        """Register *callback* for future state changes.

        The callback is invoked outside the state lock, and the immediate
        delivery is serialised with other publications.

        Args:
            callback: Called with the latest :class:`ProgressState`.
            emit_immediately: Deliver the current state right away.
        """
        with self._publish_lock:
            with self._lock:
                self._listeners.append(callback)
                state = self._state if emit_immediately else None
            if state is not None:
                self._notify([callback], state)

    def remove_listener(
        self, callback: Callable[[ProgressState], None]
    ) -> None:
        """Unregister *callback*.

        Args:
            callback: A previously registered callback.  Unknown
                callbacks are ignored.
        """
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def snapshot(self) -> ProgressState:
        """Return the current state without notifying listeners."""
        with self._lock:
            return self._state

    def flush(self) -> None:
        """Publish the current state immediately, bypassing coalescing."""
        self._publish(force=True)

    # --- internals
    def _mutate(self, **changes: object) -> None:
        """Replace state fields and publish the result."""
        with self._lock:
            self._state = self._with_overall(
                replace(self._state, **changes)
            )
        self._publish()

    def _publish(self, force: bool = False) -> None:
        """Fan the current state out to every listener.

        Capture and delivery are serialised by ``_publish_lock``, so a
        thread that read an older snapshot can never deliver it after a
        newer one.  ``_lock`` is still released before any callback runs.

        Args:
            force: Publish even when still inside the coalescing window.
        """
        with self._publish_lock:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_update
                if not force and elapsed < self._min_interval:
                    return
                self._last_update = now
                state = self._state
                listeners = list(self._listeners)
            self._notify(listeners, state)

    def _notify(
        self,
        listeners: list[Callable[[ProgressState], None]],
        state: ProgressState,
    ) -> None:
        """Invoke *listeners*, isolating failures.

        Must be called with ``_publish_lock`` held, never with ``_lock``
        held, so callbacks cannot deadlock or arrive out of order.  Stops
        early once a listener has moved the state on, so a re-entrant
        publish cannot be followed by this older snapshot.
        """
        for callback in listeners:
            if state is not self._state:
                return
            try:
                callback(state)
            except Exception:
                log.exception("Progress listener failed")

    def _with_overall(self, state: ProgressState) -> ProgressState:
        """Return *state* with the phase weight and overall filled in.

        Must be called with the lock held.

        Args:
            state: The state to enrich.

        Returns:
            A new state carrying ``weight`` and ``overall``.
        """
        if state.phase and state.total:
            fraction = state.completed / state.total
            self._phase_progress[state.phase] = max(
                0.0, min(fraction, 1.0)
            )
        return replace(
            state,
            weight=self._phases.get(state.phase, 1.0),
            overall=self._overall(),
        )

    def _overall(self) -> float | None:
        """Return the weighted progress across declared phases.

        Must be called with the lock held.

        Returns:
            A value between ``0.0`` and ``1.0``, or ``None`` when no
            phase has been declared.
        """
        total_weight = sum(self._phases.values())
        if total_weight <= 0.0:
            return None
        done = 0.0
        for name, weight in self._phases.items():
            done += weight * self._phase_progress.get(name, 0.0)
        return max(0.0, min(done / total_weight, 1.0))

    @staticmethod
    def _iter_phases(
        phases: Iterable[str | tuple[str, float]] | Mapping[str, float],
    ) -> list[tuple[str, float]]:
        """Normalise the accepted phase-plan shapes into name/weight pairs.

        Args:
            phases: Mapping, iterable of pairs, or iterable of names.

        Returns:
            A list of ``(name, weight)`` pairs.
        """
        if isinstance(phases, Mapping):
            return [
                (str(name), float(weight))
                for name, weight in phases.items()
            ]
        items: list[tuple[str, float]] = []
        for item in phases:
            if isinstance(item, str):
                items.append((item, 1.0))
            else:
                name, weight = item
                items.append((str(name), float(weight)))
        return items
