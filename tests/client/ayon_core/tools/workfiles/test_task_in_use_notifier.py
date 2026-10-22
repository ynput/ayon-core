"""Test frontend that shows notices of task in-use tracking."""
from __future__ import annotations

import threading

import pytest

pytest.importorskip("pytestqt")

from qtpy import QtCore  # noqa: E402

from ayon_core.pipeline.workfile import task_usage  # noqa: E402
from ayon_core.pipeline.workfile.task_usage import (  # noqa: E402
    TaskInUseNotice,
    TaskUsageItem,
)
from ayon_core.tools.workfiles.widgets import (  # noqa: E402
    task_in_use_dialog,
)


def _notice() -> TaskInUseNotice:
    item = TaskUsageItem(
        session_id="other-user",
        username="artist2",
        machine="machine",
        site_id="site-1",
        host_name="maya",
        workfile="sh010_anim_v001.ma",
        opened_at="2026-01-01T12:00:00+00:00",
        updated_at="2026-01-01T12:00:00+00:00",
    )
    return TaskInUseNotice([item], {"artist2": "Artist Two"})


@pytest.fixture
def shown(monkeypatch):
    """Calls of the function that shows the notice."""
    calls = []
    result = [True]

    def _show_task_in_use_notice(
        items, full_names=None, delay=1000, version_up_callback=None
    ):
        calls.append({
            "thread": QtCore.QThread.currentThread(),
            "items": items,
            "full_names": full_names,
            "version_up_callback": version_up_callback,
        })
        return result[0]

    monkeypatch.setattr(task_usage, "_acknowledged_session_ids", set())
    monkeypatch.setattr(
        task_in_use_dialog,
        "show_task_in_use_notice",
        _show_task_in_use_notice,
    )
    return calls, result


def test_notice_is_shown_in_thread_of_notifier(qtbot, shown):
    """Notice requested from other thread is not shown in that thread."""
    calls, _ = shown
    notifier = task_in_use_dialog.TaskInUseNotifier()
    notice = _notice()

    thread = threading.Thread(target=notifier.request_notice, args=(notice,))
    thread.start()
    thread.join(5)
    # Nothing is shown until the event loop is processed
    assert calls == []

    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    (call,) = calls
    assert call["thread"] is notifier.thread()
    assert call["thread"] is QtCore.QThread.currentThread()
    assert call["items"] == notice.items
    assert call["full_names"] == {"artist2": "Artist Two"}
    # User is not asked about the sessions again
    assert task_usage._acknowledged_session_ids == {"other-user"}


def test_sessions_stay_unconfirmed_if_notice_is_not_shown(qtbot, shown):
    """User is asked in the Workfiles tool if the notice was not shown."""
    calls, result = shown
    result[0] = False
    notifier = task_in_use_dialog.TaskInUseNotifier()

    notifier.request_notice(_notice())
    qtbot.waitUntil(lambda: bool(calls), timeout=5000)
    assert task_usage._acknowledged_session_ids == set()


def test_install_notifier(qtbot, monkeypatch):
    monkeypatch.setattr(task_usage, "_notice_callbacks", [])
    monkeypatch.setattr(task_in_use_dialog, "_notifier", None)

    notifier = task_in_use_dialog.install_task_in_use_notifier()
    assert task_in_use_dialog.install_task_in_use_notifier() is notifier
    assert task_usage._notice_callbacks == [notifier.request_notice]
    assert notifier.thread() is QtCore.QCoreApplication.instance().thread()
