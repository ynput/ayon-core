"""Tests for AYProgressBar and AYProgressView."""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace

import pytest

from ayon_core.ui.components.progress_bar import (
    AYProgressBar,
    AYProgressDialog,
    AYProgressView,
    ProgressBarState,
)
from ayon_core.ui.variants import AYProgressBarVariants


@dataclass(frozen=True)
class _Snapshot:
    """Structural stand-in for ``ProgressSnapshot``."""

    label: str = ""
    phase: str = ""
    completed: int = 0
    total: int | None = None
    failed: bool = False
    message: str = ""
    finished: bool = False
    overall: float | None = None


class _ProgressSource:
    """Minimal ``ProgressSource`` used to drive the view.

    The headless reporter lives in the review-desktop addon
    (``ayon_review_desktop.progress``) now, and its own tests cover
    coalescing, phase weighting, clamping and thread safety.  These tests
    only exercise the view, so snapshots are published explicitly instead
    of replicating that behaviour here.
    """

    def __init__(self, **state):
        self._state = _Snapshot(**state)
        self._listeners = []

    # --- ProgressSource ---
    def snapshot(self) -> _Snapshot:
        return self._state

    def add_listener(self, callback, emit_immediately=True):
        self._listeners.append(callback)
        if emit_immediately:
            callback(self._state)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    # --- helper
    def publish(self, **changes):
        """Replace state fields and notify listeners."""
        self._state = replace(self._state, **changes)
        for callback in list(self._listeners):
            callback(self._state)


def test_defaults(qapp):
    bar = AYProgressBar()
    assert bar.total is None and bar.current == 0
    assert bar.is_indeterminate and bar.percentage() == 0.0


def test_zero_total_is_indeterminate(qapp):
    bar = AYProgressBar(total=0)
    assert bar.is_indeterminate


def test_progress_and_completed_emitted_once(qtbot):
    bar = AYProgressBar(total=4)
    changed, done = [], []
    bar.progress_changed.connect(lambda c, t: changed.append((c, t)))
    bar.completed.connect(lambda: done.append(True))
    for value in (1, 2, 3, 4, 4, 4):
        bar.set_progress(value)
    assert changed[-1] == (4, 4)
    assert len(done) == 1, "completed must latch"


def test_total_zero_never_completes(qtbot):
    bar = AYProgressBar(total=0)
    done = []
    bar.completed.connect(lambda: done.append(True))
    bar.set_progress(3)
    assert not done


def test_reset_rearms_latch(qapp):
    bar = AYProgressBar(total=2)
    done = []
    bar.completed.connect(lambda: done.append(True))
    bar.set_progress(2)
    assert len(done) == 1

    bar.reset()
    assert bar.is_indeterminate and bar.current == 0

    bar.set_total(2)
    bar.set_progress(2)
    assert len(done) == 2, "reset must re-arm the latch"


def test_paint_renders_chunk(qtbot):
    """Regression guard: paintEvent must not raise."""
    bar = AYProgressBar(total=10)
    bar.resize(200, 12)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)

    bar.set_progress(0)
    qtbot.wait(20)
    empty = bar.grab().toImage()

    bar.set_progress(10)
    qtbot.wait(20)
    full = bar.grab().toImage()

    assert not empty.isNull()
    assert empty.pixelColor(6, 6) != full.pixelColor(6, 6)


def test_animation_only_while_visible_and_indeterminate(qtbot):
    bar = AYProgressBar()
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    assert bar.is_animating
    bar.hide()
    assert not bar.is_animating
    bar.show()
    qtbot.waitExposed(bar)
    bar.set_total(4)
    assert not bar.is_animating


def test_inline_variant_resolves(qapp):
    bar = AYProgressBar(variant=AYProgressBarVariants.Inline)
    assert bar._base_style().get("height") == 4


def test_view_applies_initial_state(qtbot):
    source = _ProgressSource(total=4, completed=2)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(source)
    qtbot.waitUntil(lambda: view.progress_bar.current == 2)


def test_view_updates_from_worker_thread(qtbot):
    source = _ProgressSource(total=50)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(source)
    assert view.progress_bar.current == 0

    completed = []
    view.progress_bar.completed.connect(lambda: completed.append(True))

    worker = threading.Thread(
        target=lambda: [source.publish(completed=step)
                        for step in range(1, 51)])
    worker.start()
    qtbot.waitUntil(lambda: view.progress_bar.current == 50, timeout=3000)
    worker.join()
    assert view.progress_bar.current == 50
    assert view.progress_bar.is_indeterminate is False
    assert completed == [True]


def test_view_queues_each_worker_snapshot(qtbot, monkeypatch):
    source = _ProgressSource(total=4)
    seen = []
    gui_thread = threading.get_ident()
    original_apply = AYProgressView._apply

    def record_apply(self, binding, state):
        seen.append((state, threading.get_ident()))
        original_apply(self, binding, state)

    monkeypatch.setattr(AYProgressView, "_apply", record_apply)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(source)

    def publish():
        source.publish(completed=1)
        source.publish(completed=2)
        source.publish(failed=True, message="Upload failed")

    worker = threading.Thread(target=publish)
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert seen == []
    qtbot.waitUntil(lambda: len(seen) == 4, timeout=3000)
    assert [state.completed for state, _ in seen] == [0, 1, 2, 2]
    assert seen[-1][0].failed
    assert all(thread_id == gui_thread for _, thread_id in seen)


@pytest.mark.parametrize("total", [None, 0, 4])
def test_view_finishes_once(qtbot, qapp, total):
    source = _ProgressSource(total=total)
    view = AYProgressView()
    qtbot.addWidget(view)
    completed = []
    view.completed.connect(lambda: completed.append(True))
    view.bind(source)
    source.publish(completed=4)
    qapp.processEvents()
    assert completed == []

    source.publish(finished=True, overall=1.0)
    source.publish()
    source.publish()
    qtbot.waitUntil(lambda: bool(completed))
    qapp.processEvents()
    assert completed == [True]
    assert view.progress_bar._state is ProgressBarState.Success

    next_source = _ProgressSource()
    view.bind(next_source)
    next_source.publish(finished=True, overall=1.0)
    qtbot.waitUntil(lambda: len(completed) == 2)
    assert completed == [True, True]


def test_view_failed_reporter_does_not_complete(qtbot, qapp):
    source = _ProgressSource(total=1)
    view = AYProgressView()
    qtbot.addWidget(view)
    completed = []
    view.completed.connect(lambda: completed.append(True))
    view.bind(source)
    source.publish(completed=1)
    source.publish(failed=True, message="Upload failed")
    source.publish(finished=True, overall=1.0)
    qapp.processEvents()
    assert completed == []
    assert view.progress_bar._state is ProgressBarState.Error


def test_dialog_closes_when_indeterminate_reporter_finishes(qtbot):
    source = _ProgressSource()
    dialog = AYProgressDialog(close_on_complete=True)
    qtbot.addWidget(dialog)
    dialog.progress_view.bind(source)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))
    dialog.show()
    assert dialog.isVisible()

    source.publish(finished=True, overall=1.0)
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert dialog.result() == dialog.DialogCode.Accepted
    assert canceled == []


def test_view_ignores_snapshots_queued_before_unbind(qtbot):
    """The view must not change from pings queued before unbind()."""
    source = _ProgressSource(total=4)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(source)
    source.publish(failed=True, message="stale failure")  # queued
    view.unbind()

    # A ping from a fresh binding drains the queue in order.
    other = _ProgressSource(total=4)
    view.bind(other)
    other.publish(completed=1)
    qtbot.waitUntil(lambda: view.progress_bar.current == 1)

    assert view._caption is None
    assert view.progress_bar._state is ProgressBarState.Normal


def test_view_ignores_queued_terminal_state_across_rebind(qtbot):
    """A rebind drops the previous source's queued terminal state.

    Otherwise it would take the completion latch and the new source's
    finish would go unnoticed.
    """
    first = _ProgressSource(total=1)
    second = _ProgressSource(total=1)
    view = AYProgressView()
    qtbot.addWidget(view)
    completed = []
    view.completed.connect(lambda: completed.append(True))

    view.bind(first)
    first.publish(finished=True, overall=1.0)  # terminal ping still queued
    view.bind(second)  # rebind before the event loop runs
    second.publish(completed=1)  # drains the queue in order
    qtbot.waitUntil(lambda: view.progress_bar.current == 1)

    assert completed == []
    assert view.progress_bar._state is not ProgressBarState.Success

    second.publish(finished=True, overall=1.0)
    qtbot.waitUntil(lambda: bool(completed))
    assert completed == [True]


def test_set_values_applies_total_and_progress_together(qtbot):
    """A new total and value must land as one change.

    Regression: applying a smaller total first clamped the old value and
    emitted a spurious ``completed`` before the real value arrived.
    """
    bar = AYProgressBar(total=10)
    changed, done = [], []
    bar.progress_changed.connect(lambda c, t: changed.append((c, t)))
    bar.completed.connect(lambda: done.append(True))

    bar.set_progress(5)
    changed.clear()
    bar.set_values(0, 3)

    assert bar.total == 3
    assert bar.current == 0
    assert not done, "a smaller total must not emit a spurious completed"
    assert changed == [(0, 3)], "one emission per set_values call"


def test_size_hint_grows_for_overlay_text(qapp):
    """Overlay text must not be clipped by the thin style height."""
    bar = AYProgressBar(total=4)
    plain = bar.sizeHint().height()

    bar.set_text("Uploading 2 of 4")
    assert bar.sizeHint().height() > plain

    bar.set_text_visible(False)
    assert bar.sizeHint().height() == plain


def test_view_follows_overall_progress(qtbot):
    """A snapshot's ``overall`` drives the bar; phases do not reset it."""
    source = _ProgressSource(
        overall=0.3, phase="export", completed=5, total=10,
    )
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(source)
    qtbot.waitUntil(lambda: view.progress_bar.current == 300)
    assert view.progress_bar.total == 1000
    assert view.value_label.text() == "30%"

    # Switching phase keeps the bar determinate at the overall value
    # instead of dropping back to an empty indeterminate bar.
    source.publish(phase="upload")
    qtbot.waitUntil(lambda: view.value_label.text() == "30%")
    assert view.progress_bar.is_indeterminate is False

    source.publish(overall=0.45, completed=2, total=4)
    qtbot.waitUntil(lambda: view.progress_bar.current == 450)
    assert view.value_label.text() == "45%"

    source.publish(finished=True, overall=1.0)
    qtbot.waitUntil(lambda: view.progress_bar.current == 1000)
    assert view.progress_bar._state is ProgressBarState.Success


def test_view_resets_previous_run_when_rebound(qtbot):
    """A rebound view must not show the previous run's state."""
    first = _ProgressSource(total=4)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(first)
    first.publish(completed=4, failed=True, message="Upload failed")
    qtbot.waitUntil(
        lambda: view.progress_bar._state is ProgressBarState.Error
    )
    assert view._caption is not None
    assert view._caption.text() == "Upload failed"

    second = _ProgressSource(total=4)
    view.bind(second)

    # Applied synchronously by bind(), before the queued snapshot.
    assert view.progress_bar.current == 0
    assert view.progress_bar.total is None
    assert view.progress_bar._state is ProgressBarState.Normal
    assert view._caption.text() == ""


def test_dialog_cancel_button_emits_canceled(qtbot):
    dialog = AYProgressDialog()
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))

    dialog.cancel_button.click()

    assert canceled == [True]
    assert dialog.result() == dialog.DialogCode.Rejected


def test_dialog_reject_emits_canceled(qtbot):
    """``reject()`` is also the path Escape takes."""
    dialog = AYProgressDialog()
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))

    dialog.reject()

    assert canceled == [True]


def test_dialog_explicit_finish_does_not_cancel(qtbot):
    dialog = AYProgressDialog()
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))

    dialog.finish()

    assert canceled == []
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.cancel_button.isEnabled() is False


def test_dialog_without_cancel_button(qtbot):
    dialog = AYProgressDialog(cancellable=False)
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))

    assert dialog.cancel_button is None
    dialog.finish()
    assert canceled == []
