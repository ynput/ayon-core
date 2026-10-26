"""Tests for AYProgressBar and AYProgressView."""
from __future__ import annotations

from ayon_core.ui.components.progress_bar import (
    AYProgressBar,
    AYProgressDialog,
    AYProgressView,
    ProgressBarState,
    ProgressTrack,
)
from ayon_core.ui.variants import AYProgressBarVariants


# --- ProgressTrack ---------------------------------------------------------


def test_track_empty():
    track = ProgressTrack.empty()
    assert track.is_empty
    assert not track.is_indeterminate
    assert track.percentage == 0.0
    assert track.caption == ""


def test_track_percentage_is_clamped():
    assert ProgressTrack(value=3, total_value=10).percentage == 30.0
    assert ProgressTrack(value=20, total_value=10).percentage == 100.0
    assert ProgressTrack(value=-1, total_value=10).percentage == 0.0
    assert ProgressTrack(value=1, total_value=0).percentage == 0.0


def test_track_caption_fallback():
    assert ProgressTrack(label="task").caption == "task"
    assert (
        ProgressTrack(label="task", phase_label="upload").caption == "upload"
    )
    assert (
        ProgressTrack(
            label="task", phase_label="upload", message="failed"
        ).caption
        == "failed"
    )


def test_track_indeterminate():
    track = ProgressTrack(value=-1, total_value=-1)
    assert track.is_indeterminate
    assert not track.is_empty


# --- AYProgressBar ---------------------------------------------------------


def test_defaults(qapp):
    bar = AYProgressBar()
    assert bar.total is None and bar.current == 0
    assert not bar.is_indeterminate
    assert bar.percentage() == 0.0


def test_track_is_applied(qapp):
    bar = AYProgressBar(
        ProgressTrack(label="task", value=3, total_value=10)
    )
    assert bar.current == 3
    assert bar.total == 10
    assert bar.percentage() == 30.0
    assert bar._state is ProgressBarState.Normal


def test_in_place_mutation_is_detected(qtbot):
    """The widget holds a reference; mutating the track must be seen."""
    track = ProgressTrack(value=1, total_value=4)
    bar = AYProgressBar(track)
    qtbot.addWidget(bar)
    assert bar.current == 1

    track.value = 4
    bar._apply_track()  # what the poll timeout calls
    assert bar.current == 4


def test_unchanged_track_is_not_reapplied(qtbot):
    bar = AYProgressBar(ProgressTrack(value=1, total_value=4))
    qtbot.addWidget(bar)
    emitted = []
    bar.track_changed.connect(emitted.append)
    bar._apply_track()
    assert emitted == []


def test_completed_is_latched_once(qtbot):
    track = ProgressTrack(value=1, total_value=2)
    bar = AYProgressBar(track)
    qtbot.addWidget(bar)
    done = []
    bar.completed.connect(lambda: done.append(True))

    track.value = 2
    bar._apply_track()
    bar._apply_track()
    assert done == [True]


def test_finished_sets_success_and_stops_polling(qtbot):
    track = ProgressTrack(value=1, total_value=2)
    bar = AYProgressBar(track)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)

    track.finished = True
    bar._apply_track()
    bar._update_polling()

    assert bar._state is ProgressBarState.Success
    assert bar.current == 2
    assert not bar._poll_timer.isActive()


def test_indeterminate_track(qapp):
    bar = AYProgressBar(ProgressTrack(value=-1, total_value=-1))
    assert bar.is_indeterminate
    assert bar.total is None


def test_empty_track_is_not_animating(qapp):
    bar = AYProgressBar()
    assert not bar.is_indeterminate


def test_caption_is_not_drawn_on_the_bar(qapp):
    """The caption belongs to the view; the bar keeps its style height."""
    bar = AYProgressBar(ProgressTrack(label="Submitting comment"))
    style_height = int(bar._base_style().get("height", 6))
    assert bar.sizeHint().height() == style_height


def test_set_progress_replaces_track(qapp):
    bar = AYProgressBar()
    bar.set_progress(ProgressTrack(value=2, total_value=4))
    assert bar.current == 2
    assert bar.total == 4


def test_reset(qapp):
    bar = AYProgressBar(ProgressTrack(value=4, total_value=4))
    bar.reset()
    assert bar.current == 0
    assert bar.total is None
    assert not bar._poll_timer.isActive()


def test_animation_only_while_visible_and_indeterminate(qtbot):
    bar = AYProgressBar(ProgressTrack(value=-1, total_value=-1))
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    assert bar.is_animating

    bar.hide()
    assert not bar.is_animating


def test_paint_renders_chunk(qtbot):
    """Regression guard: paintEvent must not raise."""
    bar = AYProgressBar(ProgressTrack(value=0, total_value=10))
    bar.resize(200, 12)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    qtbot.wait(20)
    empty = bar.grab().toImage()

    bar.set_progress(ProgressTrack(value=10, total_value=10))
    qtbot.wait(20)
    full = bar.grab().toImage()

    assert not empty.isNull()
    assert empty.pixelColor(6, 6) != full.pixelColor(6, 6)


def test_inline_variant_resolves(qapp):
    bar = AYProgressBar(variant=AYProgressBarVariants.Inline)
    assert bar._base_style().get("height") == 4


# --- AYProgressView --------------------------------------------------------


def test_view_bind_shows_track(qtbot):
    view = AYProgressView(label="Submitting")
    qtbot.addWidget(view)
    view.bind(ProgressTrack(value=2, total_value=4))
    assert view.progress_bar.current == 2
    assert view.value_label.text() == "50%"


def test_view_caption_follows_the_track(qtbot):
    view = AYProgressView(label="Submitting")
    qtbot.addWidget(view)
    track = ProgressTrack()
    view.bind(track)

    track.phase_label = "Uploading"
    view.progress_bar._apply_track()
    assert view._caption is not None
    assert view._caption.text() == "Uploading"


def test_view_polls_while_hidden(qtbot):
    """The owner shows the view once progress arrives.

    That only works if a bound view keeps reading the track while it is
    still hidden.
    """
    view = AYProgressView(label="Submitting")
    qtbot.addWidget(view)
    track = ProgressTrack()
    view.bind(track)
    assert not view.isVisible()
    assert view._poll_timer.isActive()

    track.phase_label = "Uploading"
    qtbot.waitUntil(
        lambda: view._caption is not None
        and view._caption.text() == "Uploading",
        timeout=2000,
    )


def test_view_stops_polling_when_terminal(qtbot):
    view = AYProgressView()
    qtbot.addWidget(view)
    track = ProgressTrack(value=1, total_value=2)
    view.bind(track)
    assert view._poll_timer.isActive()

    track.finished = True
    view._bar.refresh()
    assert not view._poll_timer.isActive()


def test_view_emits_completed_once(qtbot):
    view = AYProgressView()
    qtbot.addWidget(view)
    done = []
    view.completed.connect(lambda: done.append(True))

    track = ProgressTrack(value=1, total_value=2)
    view.bind(track)
    track.finished = True
    view.progress_bar._apply_track()
    view.progress_bar._apply_track()
    assert done == [True]


def test_view_unbind_stops_following(qtbot):
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(ProgressTrack(value=1, total_value=2))
    view.unbind()
    assert view._progress is None
    assert not view.progress_bar._poll_timer.isActive()


def test_view_rebind_resets_previous_state(qtbot):
    view = AYProgressView()
    qtbot.addWidget(view)
    fail_track = ProgressTrack(value=1, total_value=2)
    view.bind(fail_track)
    fail_track.failed = True
    view.progress_bar._apply_track()
    assert view.progress_bar._state is ProgressBarState.Error

    view.bind(ProgressTrack(value=0, total_value=4))
    assert view.progress_bar._state is ProgressBarState.Normal
    assert view.progress_bar.current == 0


def test_view_idle_does_not_emit(qtbot):
    """Polling an unchanged track must not repaint or re-emit."""
    view = AYProgressView()
    qtbot.addWidget(view)
    track = ProgressTrack(value=1, total_value=4)
    view.bind(track)
    emitted = []
    view.progress_bar.track_changed.connect(emitted.append)
    qtbot.wait(450)  # more than two poll intervals
    assert emitted == []


def test_high_frequency_updates_keep_the_last_value(qtbot):
    track = ProgressTrack(total_value=10_000)
    view = AYProgressView()
    qtbot.addWidget(view)
    view.bind(track)
    for i in range(1, 10_001):
        track.value = i
    view.progress_bar.refresh()
    assert view.progress_bar.current == 10_000


# --- AYProgressDialog ------------------------------------------------------


def test_dialog_bind(qtbot):
    dialog = AYProgressDialog(label="Doing")
    qtbot.addWidget(dialog)
    dialog.bind(ProgressTrack(value=1, total_value=2))
    assert dialog.progress_bar.current == 1


def test_dialog_closes_when_track_finishes(qtbot):
    dialog = AYProgressDialog(close_on_complete=True)
    qtbot.addWidget(dialog)
    canceled = []
    dialog.canceled.connect(lambda: canceled.append(True))

    track = ProgressTrack(value=1, total_value=2)
    dialog.bind(track)
    dialog.show()
    assert dialog.isVisible()

    track.finished = True
    dialog.progress_bar._apply_track()
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert canceled == []
