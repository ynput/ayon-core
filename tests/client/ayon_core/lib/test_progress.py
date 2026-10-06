"""Tests for the headless progress reporter."""
from __future__ import annotations

import threading

from ayon_core.lib.progress import ProgressReporter


def test_indeterminate_by_default():
    reporter = ProgressReporter()
    assert reporter.snapshot().total is None
    assert reporter.snapshot().completed == 0


def test_step_counts_and_clamps():
    reporter = ProgressReporter(total=3)
    for _ in range(5):
        reporter.step()
    assert reporter.snapshot().completed == 3


def test_listener_is_notified_on_every_change():
    seen = []
    reporter = ProgressReporter(total=2, min_interval=0.0)
    reporter.add_listener(seen.append, emit_immediately=False)
    reporter.step()
    reporter.finish()
    assert [s.completed for s in seen] == [1, 2]
    assert seen[-1].finished


def test_phase_can_change():
    reporter = ProgressReporter(total=4)
    reporter.set_phase("export", weight=0.6)
    reporter.set_phase("upload", weight=0.4)
    assert reporter.snapshot().phase == "upload"


def test_finish_and_fail_are_terminal_once():
    reporter = ProgressReporter(total=1, min_interval=0.0)
    seen = []
    reporter.add_listener(seen.append, emit_immediately=False)
    reporter.finish()
    reporter.finish()
    reporter.fail("late")
    assert sum(s.finished for s in seen) == 1
    assert not any(s.failed for s in seen)


def test_listener_removed_during_notify_does_not_break():
    reporter = ProgressReporter(total=1, min_interval=0.0)
    seen = []

    def noisy(state):
        seen.append(state)
        reporter.remove_listener(noisy)

    reporter.add_listener(noisy, emit_immediately=False)
    reporter.step()          # must not raise
    assert len(seen) == 1


def test_raising_listener_does_not_propagate():
    reporter = ProgressReporter(total=1, min_interval=0.0)
    reporter.add_listener(lambda s: (_ for _ in ()).throw(ValueError("boom")),
                          emit_immediately=False)
    reporter.step()          # must not raise


def test_thread_safety():
    reporter = ProgressReporter(total=400, min_interval=0.0)
    threads = [
        threading.Thread(target=lambda: [reporter.step() for _ in range(100)])
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert reporter.snapshot().completed == 400


def test_terminal_state_set_from_callback_is_delivered():
    """A callback that ends the run must still receive the final state.

    The re-entrant ``finish()`` cannot deliver anything itself, so the
    trailing pass of the running delivery has to send it.
    """
    reporter = ProgressReporter(total=1)
    seen = []

    def listener(state):
        seen.append((state.completed, state.finished))
        if state.completed == state.total and not state.finished:
            reporter.finish()

    reporter.add_listener(listener, emit_immediately=False)
    reporter.step()

    assert seen == [(1, False), (1, True)]


def _late_mutations(reporter) -> None:
    """Drive every mutating entry point once."""
    reporter.step()
    reporter.set_progress(0)
    reporter.set_total(5)
    reporter.set_phase("upload", weight=2.0)
    reporter.set_phases([("extra", 1.0)])


def test_mutations_after_finish_are_ignored():
    """A finished run cannot be altered by a late update."""
    reporter = ProgressReporter(total=2, min_interval=0.0)
    seen = []
    reporter.add_listener(seen.append, emit_immediately=False)
    reporter.step()
    reporter.finish()
    published = list(seen)

    _late_mutations(reporter)

    assert seen == published
    state = reporter.snapshot()
    assert state.completed == 2
    assert state.total == 2
    assert state.phase == ""
    assert state.finished is True
    assert state.failed is False


def test_mutations_after_failure_are_ignored():
    """A failed run cannot be altered by a late update."""
    reporter = ProgressReporter(total=2, min_interval=0.0)
    seen = []
    reporter.add_listener(seen.append, emit_immediately=False)
    reporter.step()
    reporter.fail("Upload failed")
    published = list(seen)

    _late_mutations(reporter)

    assert seen == published
    state = reporter.snapshot()
    assert state.completed == 1
    assert state.total == 2
    assert state.phase == ""
    assert state.failed is True
    assert state.finished is False
