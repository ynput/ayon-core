"""Show which workfiles of a task are in use by a running application.

PROTOTYPE: Used by views that list workfiles of a task with avatar of
the user who made the last change. The avatar gets a ring if the workfile
is opened in a running application, and a popup with the sessions is
shown when the avatar is hovered.

The information is not needed to show the workfiles, so it never delays
them. Sessions are requested in the shared task queue after the view was
filled, and the view is only repainted when they arrive.

The indicator is UI only. It does not know where the sessions come from,
a tool passes it a function that receives them from its controller.
"""
from __future__ import annotations

import datetime
import logging
import os
import typing
from typing import Any, Callable, Hashable, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.style import load_stylesheet
from ayon_core.ui.components import AYLabel, AYVBoxLayout
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.workfile.task_usage import TaskUsageItem

    # Function called in a worker thread that returns sessions working on
    #   a task and full names of their users by username
    FetchSessions = Callable[
        [], tuple[list[TaskUsageItem], dict[str, str]]
    ]

log = logging.getLogger(__name__)

# The user who has the workfile opened is the user shown by the avatar
SAME_USER_COLOR = "#6be1ac"
# The workfile is opened by a different user than shown by the avatar
OTHER_USER_COLOR = "#ffb86b"
# Sessions are requested again while the view is visible
REFRESH_INTERVAL_MS = 30 * 1000
# Do not delay showing of the workfiles by the request
REQUEST_DELAY_MS = 50
_MAX_CACHED_PIXMAPS = 256


def group_items_by_workfile(
    items: list[TaskUsageItem],
) -> dict[str, list[TaskUsageItem]]:
    """Group sessions by filename of the workfile they have opened.

    Args:
        items (list[TaskUsageItem]): Sessions working on a task.

    Returns:
        dict[str, list[TaskUsageItem]]: Sessions by lowered filename.
            Sessions without opened workfile are skipped.

    """
    output: dict[str, list[TaskUsageItem]] = {}
    for item in items:
        if not item.workfile:
            continue
        filename = os.path.basename(item.workfile).lower()
        output.setdefault(filename, []).append(item)
    return output


def is_in_use_by_user(
    items: list[TaskUsageItem], username: Optional[str]
) -> bool:
    """Any of the sessions is a session of the user."""
    return any(item.username == username for item in items)


class TaskInUseToolTip(QtWidgets.QFrame):
    """Popup with sessions that have a workfile opened."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent, QtCore.Qt.ToolTip)
        self.setObjectName("TaskInUseToolTip")
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._layout = AYVBoxLayout(self, margin=12, spacing=10)
        self._content: Optional[QtWidgets.QWidget] = None
        self.setStyleSheet(
            load_stylesheet()
            + "#TaskInUseToolTip {border: 1px solid #4b5564;}"
        )

    def set_sessions(
        self,
        items: list[TaskUsageItem],
        full_names: dict[str, str],
        author: Optional[str],
        author_label: Optional[str],
    ) -> None:
        """Change content of the popup.

        Args:
            items (list[TaskUsageItem]): Sessions with opened workfile.
            full_names (dict[str, str]): Full names of users by username.
            author (Optional[str]): Username of the user who made the
                last change of the workfile.
            author_label (Optional[str]): Label of the author.

        """
        # Avoid import of the Workfiles tool until a popup is needed
        from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (
            SessionWidget,
        )

        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.setVisible(False)
            self._content.deleteLater()

        content = QtWidgets.QWidget(self)
        layout = AYVBoxLayout(content, margin=0, spacing=10)
        layout.addWidget(
            AYLabel("Opened in a running application", parent=content), 0
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        for item in items:
            layout.addWidget(
                SessionWidget(
                    item, full_names.get(item.username), now, content
                ),
                0,
            )

        if author and not is_in_use_by_user(items, author):
            layout.addWidget(
                AYLabel(
                    f"Different from {author_label or author},"
                    " who saved this workfile last.",
                    text_color=OTHER_USER_COLOR,
                    parent=content,
                ),
                0,
            )

        self._layout.addWidget(content, 0)
        self._content = content
        self.adjustSize()


class TaskInUseIndicator(QtCore.QObject):
    """Know which workfiles shown in a view are in use.

    The indicator receives sessions of a task in the background and tells
    a delegate of the view which workfiles are opened in a running
    application. The view is repainted when the sessions change.

    Args:
        view (QtWidgets.QAbstractItemView): View with workfiles of a task.
            First column of a row must have the filename in display role.
        avatar_column (int): Column that shows avatar of the user.
        username_role (int): Role with username of the user shown by the
            avatar, received from the first column.
        user_label_role (Optional[int]): Role with label of the user.

    """
    sessions_changed = QtCore.Signal()

    def __init__(
        self,
        view: QtWidgets.QAbstractItemView,
        avatar_column: int,
        username_role: int,
        user_label_role: Optional[int] = None,
    ):
        super().__init__(view)
        self._view = view
        self._avatar_column = avatar_column
        self._username_role = username_role
        self._user_label_role = user_label_role

        self._context: Optional[Hashable] = None
        self._fetch_sessions: Optional[FetchSessions] = None
        self._request_id = 0
        self._context_id = f"task_in_use_indicator_{id(self)}"
        self._items_by_filename: dict[str, list[TaskUsageItem]] = {}
        self._full_names: dict[str, str] = {}
        self._ring_pixmaps: dict[tuple, QtGui.QPixmap] = {}

        self._tooltip: Optional[TaskInUseToolTip] = None
        self._tooltip_index = QtCore.QPersistentModelIndex()

        request_timer = QtCore.QTimer(self)
        request_timer.setSingleShot(True)
        request_timer.setInterval(REQUEST_DELAY_MS)
        request_timer.timeout.connect(self._request)

        refresh_timer = QtCore.QTimer(self)
        refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        refresh_timer.timeout.connect(self._on_refresh_timer)
        refresh_timer.start()

        self._request_timer = request_timer
        self._refresh_timer = refresh_timer

        view.viewport().installEventFilter(self)
        view.viewport().setMouseTracking(True)

    def set_context(
        self,
        context: Optional[Hashable],
        fetch_sessions: Optional[FetchSessions] = None,
    ) -> None:
        """Change task of workfiles shown in the view.

        Should be called when the view was filled with workfiles. Known
        sessions are dropped if the context did change. Sessions are
        received in the background.

        Args:
            context (Optional[Hashable]): Identifier of the task, e.g. task
                id. Nothing is shown if is not passed.
            fetch_sessions (Optional[FetchSessions]): Function that returns
                sessions working on the task and full names of their
                users. Is called in a worker thread.

        """
        if context is None:
            fetch_sessions = None
        if context != self._context:
            self._context = context
            self._set_sessions({}, {})
        self._fetch_sessions = fetch_sessions
        self.refresh()

    def refresh(self) -> None:
        """Receive sessions of current task in the background."""
        self._request_id += 1
        self._request_timer.start()

    def get_sessions(self, index: QtCore.QModelIndex) -> list[TaskUsageItem]:
        """Sessions that have opened the workfile of an index."""
        if not self._items_by_filename:
            return []
        filename = index.sibling(index.row(), 0).data(QtCore.Qt.DisplayRole)
        if not filename:
            return []
        return self._items_by_filename.get(str(filename).lower(), [])

    def decorate_avatar(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        """Add ring to the avatar of an item with workfile in use.

        Meant to be called from 'initStyleOption' of an item delegate
        after the avatar was set as the decoration of the item.
        """
        items = self.get_sessions(index)
        if not items or option.icon.isNull():
            return
        username = index.sibling(index.row(), 0).data(self._username_role)
        color = OTHER_USER_COLOR
        if is_in_use_by_user(items, username):
            color = SAME_USER_COLOR
        option.icon = QtGui.QIcon(self._get_ring_pixmap(option.icon, color))

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type == QtCore.QEvent.ToolTip:
            if self._show_tooltip(event.pos()):
                return True
            self._hide_tooltip()

        elif event_type == QtCore.QEvent.MouseMove:
            if self._tooltip_index.isValid():
                index = self._view.indexAt(event.pos())
                if (
                    index.column() != self._avatar_column
                    or index.row() != self._tooltip_index.row()
                    or index.parent() != self._tooltip_index.parent()
                ):
                    self._hide_tooltip()

        elif event_type in (
            QtCore.QEvent.Leave,
            QtCore.QEvent.Wheel,
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.Hide,
            QtCore.QEvent.WindowDeactivate,
        ):
            self._hide_tooltip()
        return super().eventFilter(obj, event)

    def _show_tooltip(self, pos: QtCore.QPoint) -> bool:
        index = self._view.indexAt(pos)
        if not index.isValid() or index.column() != self._avatar_column:
            return False
        items = self.get_sessions(index)
        if not items:
            return False

        first_index = index.sibling(index.row(), 0)
        author_label = None
        if self._user_label_role is not None:
            author_label = first_index.data(self._user_label_role)

        if self._tooltip is None:
            self._tooltip = TaskInUseToolTip(self._view)
        self._tooltip.set_sessions(
            items,
            self._full_names,
            first_index.data(self._username_role),
            author_label,
        )
        rect = self._view.visualRect(index)
        global_pos = self._view.viewport().mapToGlobal(rect.bottomLeft())
        self._tooltip.move(global_pos + QtCore.QPoint(0, 4))
        self._tooltip.show()
        self._tooltip_index = QtCore.QPersistentModelIndex(index)
        return True

    def _hide_tooltip(self) -> None:
        self._tooltip_index = QtCore.QPersistentModelIndex()
        if self._tooltip is not None:
            self._tooltip.hide()

    def _on_refresh_timer(self) -> None:
        if self._fetch_sessions is not None and self._view.isVisible():
            self.refresh()

    def _request(self) -> None:
        fetch_sessions = self._fetch_sessions
        if fetch_sessions is None:
            return

        request_id = self._request_id
        task_queue = get_task_queue()
        # Drop pending requests of previous task
        task_queue.clear_context_tasks(self._context_id)
        task_queue.enqueue(AsyncTask(
            name="fetch_task_in_use",
            function=lambda: _call_fetch_sessions(fetch_sessions),
            callback=lambda result: self._on_fetched(request_id, result),
            # Less important than anything else in the queue
            priority=10,
            context_id=self._context_id,
            cancellable=True,
        ))

    def _on_fetched(self, request_id: int, result: Any) -> None:
        # Task did change meanwhile or the request failed
        if request_id != self._request_id or result is None:
            return
        items, full_names = result
        self._set_sessions(group_items_by_workfile(items), full_names)

    def _set_sessions(
        self,
        items_by_filename: dict[str, list[TaskUsageItem]],
        full_names: dict[str, str],
    ) -> None:
        self._full_names = full_names
        if items_by_filename == self._items_by_filename:
            return
        self._items_by_filename = items_by_filename
        self._hide_tooltip()
        self._view.viewport().update()
        self.sessions_changed.emit()

    def _get_ring_pixmap(self, icon: QtGui.QIcon, color: str) -> QtGui.QPixmap:
        sizes = icon.availableSizes()
        if not sizes:
            return QtGui.QPixmap()
        source = icon.pixmap(sizes[0])
        key = (source.cacheKey(), color)
        pixmap = self._ring_pixmaps.get(key)
        if pixmap is not None:
            return pixmap

        pixmap = QtGui.QPixmap(source)
        ratio = pixmap.devicePixelRatio() or 1.0
        size = pixmap.width() / ratio
        width = max(2.0, size / 9.0)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(color))
        pen.setWidthF(width)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        half = width / 2.0
        painter.drawEllipse(
            QtCore.QRectF(half, half, size - width, size - width)
        )
        painter.end()

        if len(self._ring_pixmaps) >= _MAX_CACHED_PIXMAPS:
            self._ring_pixmaps.clear()
        self._ring_pixmaps[key] = pixmap
        return pixmap


def _call_fetch_sessions(fetch_sessions: FetchSessions) -> Any:
    """Called in a worker thread."""
    try:
        return fetch_sessions()
    except Exception:
        log.debug("Failed to receive task in-use sessions.", exc_info=True)
        return None
