"""Notice inside the application about other users working on a task."""
from __future__ import annotations

import logging
import typing

from qtpy import QtWidgets, QtCore

from ayon_core.pipeline.workfile.task_usage import (
    register_task_in_use_notice_callback,
)

from .dialog import TaskInUseDialog

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.workfile.task_usage import TaskUsageItem

log = logging.getLogger(__name__)


# Keep reference to the shown notice
_notice_dialog: TaskInUseDialog | None = None


def show_task_in_use_notice(
    items: list[TaskUsageItem],
    delay: int = 1000,
) -> None:
    """Inform user that other users are working on the current task.

    The dialog is not modal and is shown when the Qt event loop is free,
    so it does not block startup of the application. Nothing happens if
    Qt application with UI is not available.

    Args:
        items (list[TaskUsageItem]): Sessions of other users working on
            the task.
        delay (int): Delay in milliseconds before the dialog is shown.

    """
    app = QtWidgets.QApplication.instance()
    # 'QCoreApplication' is returned in applications without UI
    if not isinstance(app, QtWidgets.QApplication):
        return

    def _on_finished(dialog):
        global _notice_dialog

        if _notice_dialog is dialog:
            _notice_dialog = None
        dialog.deleteLater()

    def _show():
        global _notice_dialog

        if _notice_dialog is not None:
            _notice_dialog.close()
        dialog = TaskInUseDialog(items, notice_only=True)
        dialog.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        # The notice does not keep the application running when its main
        #   window is closed, e.g. Silhouette quits on last window closed
        dialog.setAttribute(QtCore.Qt.WA_QuitOnClose, False)
        dialog.finished.connect(lambda *_: _on_finished(dialog))
        _notice_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    QtCore.QTimer.singleShot(delay, _show)


class TaskInUseNotifier(QtCore.QObject):
    """Show notices about task in use requested from other threads.

    Task in-use tracking does requests to the server in a background
    thread, where UI can't be shown. The sessions are passed with a queued
    signal to the thread of this object, which should be the thread of Qt
    application. The notice is shown when the event loop of the
    application is processed.
    """
    _notice_requested = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._notice_requested.connect(
            self._on_notice_request, QtCore.Qt.QueuedConnection
        )

    def request_notice(self, items: list[TaskUsageItem]) -> None:
        """Request to show a notice, can be called from any thread."""
        self._notice_requested.emit(items)

    def _on_notice_request(self, items: list[TaskUsageItem]) -> None:
        try:
            show_task_in_use_notice(items)
        except Exception:
            log.warning("Failed to show task in-use notice.", exc_info=True)


_notifier = None


def install_task_in_use_notifier() -> TaskInUseNotifier:
    """Show notices of task in-use tracking in the application.

    Is called by host integrations based on Qt, e.g. in 'install' of the
    host, so the notice can be shown when the tracking is started.

    Must be called from the main thread of the application, the notices
    are shown in the thread of Qt application.

    Returns:
        TaskInUseNotifier: Object that is showing the notices.

    """
    global _notifier

    if _notifier is not None:
        return _notifier

    notifier = TaskInUseNotifier()
    app = QtCore.QCoreApplication.instance()
    if app is not None and notifier.thread() is not app.thread():
        notifier.moveToThread(app.thread())

    register_task_in_use_notice_callback(notifier.request_notice)
    _notifier = notifier
    return notifier
