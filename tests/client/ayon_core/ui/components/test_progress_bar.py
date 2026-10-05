"""Tests for AYProgressBar and AYProgressView."""
from __future__ import annotations

import threading

import pytest

from ayon_core.lib.progress import ProgressReporter
from ayon_core.ui.components.progress_bar import (
    AYProgressBar,
    AYProgressDialog,
    AYProgressView,
    ProgressBarState,
)
from ayon_core.ui.variants import AYProgressBarVariants


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
    reporter = ProgressReporter(total=4, min_interval=0.0)
    reporter.set_progress(2)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(reporter)
    qtbot.waitUntil(lambda: view.progress_bar.current == 2)


def test_view_updates_from_worker_thread(qtbot):
    reporter = ProgressReporter(total=50, min_interval=0.0)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(reporter)
    assert view.progress_bar.current == 0

    completed = []
    view.progress_bar.completed.connect(lambda: completed.append(True))

    worker = threading.Thread(
        target=lambda: [reporter.step() for _ in range(50)])
    worker.start()
    qtbot.waitUntil(lambda: view.progress_bar.current == 50, timeout=3000)
    worker.join()
    assert view.progress_bar.current == 50
    assert view.progress_bar.is_indeterminate is False
    assert completed == [True]


def test_view_queues_each_worker_snapshot(qtbot, monkeypatch):
    reporter = ProgressReporter(total=4, min_interval=0.0)
    seen = []
    gui_thread = threading.get_ident()
    original_apply = AYProgressView._apply

    def record_apply(self, state):
        seen.append((state, threading.get_ident()))
        original_apply(self, state)

    monkeypatch.setattr(AYProgressView, "_apply", record_apply)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(reporter)

    def publish():
        reporter.set_progress(1)
        reporter.set_progress(2)
        reporter.fail("Upload failed")

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
def test_view_reporter_finishes_once(qtbot, qapp, total):
    reporter = ProgressReporter(total=total, min_interval=0.0)
    view = AYProgressView()
    qtbot.addWidget(view)
    completed = []
    view.completed.connect(lambda: completed.append(True))
    view.bind(reporter)
    reporter.set_progress(4)
    qapp.processEvents()
    assert completed == []

    reporter.finish()
    reporter.flush()
    reporter.flush()
    qtbot.waitUntil(lambda: bool(completed))
    qapp.processEvents()
    assert completed == [True]
    assert view.progress_bar._state is ProgressBarState.Success

    next_reporter = ProgressReporter(min_interval=0.0)
    view.bind(next_reporter)
    next_reporter.finish()
    qtbot.waitUntil(lambda: len(completed) == 2)
    assert completed == [True, True]


def test_view_failed_reporter_does_not_complete(qtbot, qapp):
    reporter = ProgressReporter(total=1, min_interval=0.0)
    view = AYProgressView()
    qtbot.addWidget(view)
    completed = []
    view.completed.connect(lambda: completed.append(True))
    view.bind(reporter)
    reporter.set_progress(1)
    reporter.fail("Upload failed")
    reporter.finish()
    qapp.processEvents()
    assert completed == []
    assert view.progress_bar._state is ProgressBarState.Error


def test_dialog_closes_when_indeterminate_reporter_finishes(qtbot):
    reporter = ProgressReporter()
    dialog = AYProgressDialog(close_on_complete=True)
    qtbot.addWidget(dialog)
    dialog.progress_view.bind(reporter)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))
    dialog.show()
    assert dialog.isVisible()

    reporter.finish()
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert dialog.result() == dialog.DialogCode.Accepted
    assert canceled == []
