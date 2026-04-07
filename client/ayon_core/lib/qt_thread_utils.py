# -*- coding: utf-8 -*-
"""Qt main-thread scheduling helpers for host integrations."""

from typing import Any, Callable


def schedule_on_qt_main_thread(fn: Callable[[], Any]) -> None:
    """Run ``fn`` on the Qt main thread soon, or immediately if no Qt app exists.

    Uses ``QTimer.singleShot(0, ...)`` when ``QApplication.instance()`` is
    available; otherwise calls ``fn()`` on the current thread (headless/tests).
    """
    try:
        from qtpy.QtCore import QTimer
        from qtpy.QtWidgets import QApplication

        if QApplication.instance() is not None:
            QTimer.singleShot(0, fn)
            return
    except Exception:
        pass
    fn()
