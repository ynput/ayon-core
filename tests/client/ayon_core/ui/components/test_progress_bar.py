"""Tests for AYProgressBar."""
from __future__ import annotations

from ayon_core.ui.components.progress_bar import (
    AYProgressBar,
    ProgressBarState,
)
from ayon_core.ui.variants import AYProgressBarVariants


# --- AYProgressBar ---------------------------------------------------------


def test_defaults(qapp):
    bar = AYProgressBar()
    assert bar.value() == 0
    assert bar.maximum() == 0
    assert bar.state() is ProgressBarState.Normal
    assert not bar.is_indeterminate()
    assert bar.percentage() == 0.0


def test_maximum_is_keyword_only(qapp):
    bar = AYProgressBar(maximum=10)
    assert bar.maximum() == 10
    assert bar.parent() is None


def test_value_and_percentage(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_value(3)
    assert bar.value() == 3
    assert bar.percentage() == 30.0


def test_percentage_is_clamped(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_value(15)
    assert bar.percentage() == 100.0


def test_zero_maximum_is_empty(qapp):
    bar = AYProgressBar()
    bar.set_value(5)
    assert not bar.is_indeterminate()
    assert bar.percentage() == 0.0


def test_negative_value_is_indeterminate(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_value(-1)
    assert bar.is_indeterminate()
    assert bar.percentage() == 0.0


def test_negative_maximum_is_indeterminate(qapp):
    bar = AYProgressBar(maximum=-1)
    bar.set_value(5)
    assert bar.is_indeterminate()
    assert bar.percentage() == 0.0


def test_value_changed_only_on_change(qapp):
    bar = AYProgressBar(maximum=10)
    emitted = []
    bar.value_changed.connect(emitted.append)
    bar.set_value(4)
    bar.set_value(4)
    bar.set_value(5)
    assert emitted == [4, 5]


def test_maximum_changed_only_on_change(qapp):
    bar = AYProgressBar(maximum=10)
    emitted = []
    bar.maximum_changed.connect(emitted.append)
    bar.set_maximum(10)
    bar.set_maximum(20)
    assert emitted == [20]
    assert bar.maximum() == 20


def test_set_state(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_state(ProgressBarState.Error)
    assert bar.state() is ProgressBarState.Error


def test_size_hint_follows_style_height(qapp):
    bar = AYProgressBar(show_value=False)
    style_height = int(bar._base_style().get("height", 6))
    assert bar.sizeHint().height() == style_height


def test_animation_only_while_visible_and_indeterminate(qtbot):
    bar = AYProgressBar(maximum=10)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    assert not bar.is_animating()

    bar.set_value(-1)
    assert bar.is_animating()

    bar.hide()
    assert not bar.is_animating()

    bar.show()
    qtbot.waitExposed(bar)
    assert bar.is_animating()

    bar.set_value(3)
    assert not bar.is_animating()


def test_hidden_indeterminate_bar_does_not_animate(qapp):
    bar = AYProgressBar(maximum=-1)
    assert bar.is_indeterminate()
    assert not bar.is_animating()


def test_paint_renders_chunk(qtbot):
    """Regression guard: paintEvent must not raise."""
    bar = AYProgressBar(maximum=10)
    bar.resize(200, 12)
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    qtbot.wait(20)
    empty = bar.grab().toImage()

    bar.set_value(10)
    qtbot.wait(20)
    full = bar.grab().toImage()

    assert not empty.isNull()
    assert empty.pixelColor(6, 6) != full.pixelColor(6, 6)


def test_state_changes_chunk_colour(qtbot):
    bar = AYProgressBar(maximum=10)
    bar.resize(200, 12)
    qtbot.addWidget(bar)
    bar.set_value(10)
    bar.show()
    qtbot.waitExposed(bar)
    normal = bar.grab().toImage().pixelColor(100, 6)

    bar.set_state(ProgressBarState.Error)
    error = bar.grab().toImage().pixelColor(100, 6)
    assert normal != error


def test_text_follows_value_and_maximum(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_value(5)
    assert bar.text() == "50%"

    bar.set_maximum(20)
    assert bar.text() == "25%"

    bar.set_maximum(-1)
    assert bar.text() == ""


def test_text_is_empty_while_indeterminate(qapp):
    bar = AYProgressBar(maximum=10)
    bar.set_value(-1)
    assert bar.text() == ""


def test_value_is_shown_by_default(qapp):
    bar = AYProgressBar()
    assert bar.show_value()
    assert bar.sizeHint().height() >= bar.fontMetrics().height()


def test_show_value_reserves_space(qapp):
    bar = AYProgressBar(maximum=10, show_value=False)
    plain_hint = bar.sizeHint()

    bar.set_show_value(True)
    hint = bar.sizeHint()
    assert hint.width() > plain_hint.width()
    assert hint.height() >= bar.fontMetrics().height()
    assert bar.minimumSizeHint().width() > 40


def test_show_value_shortens_track(qtbot):
    """The percentage is drawn right of the track, not over it."""
    bar = AYProgressBar(maximum=10, show_value=False)
    bar.resize(200, 20)
    qtbot.addWidget(bar)
    bar.set_value(10)
    bar.show()
    qtbot.waitExposed(bar)
    full = bar.grab().toImage()
    style = bar._base_style()
    # Right end of a full track is chunk coloured.
    chunk = full.pixelColor(196, 10)

    bar.set_show_value(True)
    with_value = bar.grab().toImage()
    track_end = 200 - bar._value_space(style)
    assert with_value.pixelColor(track_end - 4, 10) == chunk
    assert with_value.pixelColor(track_end + 2, 10) != chunk


def test_inline_variant_resolves(qapp):
    bar = AYProgressBar(variant=AYProgressBarVariants.Inline)
    assert bar._base_style().get("height") == 4
