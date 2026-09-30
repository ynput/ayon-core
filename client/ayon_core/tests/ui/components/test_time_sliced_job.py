"""Tests for 'TimeSlicedJob'."""

from __future__ import annotations

from unittest.mock import Mock

from ayon_core.ui.components.time_sliced_job import TimeSlicedJob


def _run(qtbot, generator) -> Mock:
    job = TimeSlicedJob(generator, budget_ms=1)
    finished = Mock()
    job.finished.connect(finished)
    job.start()
    qtbot.waitUntil(lambda: not job.is_running())
    return finished


def test_finished_with_success(qtbot):
    done = []

    def _work():
        for idx in range(1000):
            done.append(idx)
            yield

    finished = _run(qtbot, _work())

    finished.assert_called_once_with(True)
    assert len(done) == 1000


def test_finished_with_failure(qtbot):
    def _work():
        yield
        raise ValueError("Failed")

    finished = _run(qtbot, _work())

    finished.assert_called_once_with(False)


def test_cancel_does_not_emit_finished(qtbot):
    def _work():
        while True:
            yield

    job = TimeSlicedJob(_work(), budget_ms=1)
    finished = Mock()
    job.finished.connect(finished)
    job.start()
    qtbot.wait(20)
    job.cancel()
    qtbot.wait(20)

    assert not job.is_running()
    finished.assert_not_called()
