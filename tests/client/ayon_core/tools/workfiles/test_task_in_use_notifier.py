"""Test frontend that shows notices of task in-use tracking."""
from __future__ import annotations

import threading

import pytest

pytest.importorskip("pytestqt")

from qtpy import QtCore  # noqa: E402

from ayon_core.pipeline.workfile import task_usage  # noqa: E402
from ayon_core.pipeline.workfile.task_usage import (  # noqa: E402
    TaskUsageItem,
)
from ayon_core.tools.workfiles.widgets import (  # noqa: E402
    task_in_use_dialog,
)


class _App(QtCore.QObject):
    """Stand-in of Qt application with its quit signal."""
    aboutToQuit = QtCore.Signal()


def _items() -> list[TaskUsageItem]:
    return [
        TaskUsageItem(
            session_id="other-user",
            username="artist2",
            machine="machine",
            host_name="maya",
            workfile="sh010_anim_v001.ma",
            opened_at="2026-01-01T12:00:00+00:00",
            updated_at="2026-01-01T12:00:00+00:00",
            full_name="Artist Two",
        )
    ]


@pytest.fixture
def shown(monkeypatch):
    """Calls of the function that shows the notice."""
    calls = []

    def _show_task_in_use_notice(items, delay=1000):
        calls.append({
            "thread": QtCore.QThread.currentThread(),
            "items": items,
        })

    monkeypatch.setattr(
        task_in_use_dialog,
        "show_task_in_use_notice",
        _show_task_in_use_notice,
    )
    return calls


def test_notice_is_shown_in_thread_of_notifier(qtbot, shown):
    """Notice requested from other thread is not shown in that thread."""
    calls = shown
    notifier = task_in_use_dialog.TaskInUseNotifier()
    items = _items()

    thread = threading.Thread(target=notifier.request_notice, args=(items,))
    thread.start()
    thread.join(5)
    # Nothing is shown until the event loop is processed
    assert calls == []

    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    (call,) = calls
    assert call["thread"] is notifier.thread()
    assert call["thread"] is QtCore.QThread.currentThread()
    assert call["items"] == items


def test_install_notifier(qtbot, monkeypatch):
    monkeypatch.setattr(task_usage, "_notice_callbacks", [])
    monkeypatch.setattr(task_in_use_dialog, "_notifier", None)
    uninstalled = []
    monkeypatch.setattr(
        task_usage,
        "uninstall_task_usage_tracker",
        lambda: uninstalled.append(True),
    )
    # Quit of the application used by other tests is not emitted
    app = _App()
    with monkeypatch.context() as patch:
        patch.setattr(QtCore.QCoreApplication, "instance", lambda: app)
        notifier = task_in_use_dialog.install_task_in_use_notifier()

    assert task_in_use_dialog.install_task_in_use_notifier() is notifier
    assert task_usage._notice_callbacks == [notifier.request_notice]
    assert notifier.thread() is app.thread()

    # Tasks are released when the application quits
    app.aboutToQuit.emit()
    assert uninstalled == [True]
