from __future__ import annotations

import datetime
import typing

from qtpy import QtWidgets, QtGui, QtCore

from ayon_core.style import load_stylesheet, get_app_icon_path
from ayon_core.ui.components import (
    AYButton,
    AYLabel,
    AYHBoxLayout,
    AYVBoxLayout
)
from ayon_core.ui.components.user_image import AYUserImage

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.workfile.task_usage import TaskUsageItem

AVATAR_SIZE = 36
# Shorter difference of opened and last update time is not shown
MIN_SAVED_DIFFERENCE = datetime.timedelta(minutes=1)

_avatar_cache = None


def _get_avatar_cache():
    """Shared cache of user avatars.

    Returns:
        Optional[UserAvatarCache]: Cache or None if the cache is not
            available in current Qt binding.

    """
    global _avatar_cache

    if _avatar_cache is None:
        try:
            from ayon_core.ui.components.user_avatars import UserAvatarCache

            _avatar_cache = UserAvatarCache()
        except Exception:
            _avatar_cache = False
    return _avatar_cache or None


def get_time_ago_label(
    value: datetime.datetime, now: datetime.datetime
) -> str:
    """Short label of how long ago a time was.

    Args:
        value (datetime.datetime): Time in the past.
        now (datetime.datetime): Current time.

    Returns:
        str: Label, e.g. '5 min ago', '2 h ago' or '3 days ago'.

    """
    seconds = int((now - value).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} h ago"
    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


class _UserAvatarLabel(QtWidgets.QLabel):
    """Avatar of a user.

    Initials are shown until the avatar is downloaded, or if the avatar is
    not available for current user.
    """
    def __init__(
        self,
        username: str,
        full_name: str,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)
        self.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self._username = username
        self._full_name = full_name

        cache = _get_avatar_cache()
        if cache is not None:
            cache.avatar_updated.connect(self._on_avatar_update)
        self._update_pixmap()

    def _on_avatar_update(self, username: str) -> None:
        if username == self._username:
            self._update_pixmap()

    def _update_pixmap(self) -> None:
        cache = _get_avatar_cache()
        if cache is not None:
            pixmap = cache.pixmap(
                self._username, self._full_name, AVATAR_SIZE
            )
        else:
            widget = AYUserImage(
                name=self._username,
                full_name=self._full_name,
                size=AVATAR_SIZE,
                outline=False,
            )
            pixmap = widget.pxm
            widget.deleteLater()

        if pixmap is not None:
            self.setPixmap(pixmap)


class _SessionWidget(QtWidgets.QWidget):
    """Session of a user working on the task."""

    def __init__(
        self,
        item: TaskUsageItem,
        full_name: str | None,
        now: datetime.datetime,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)

        user_label = full_name or item.username
        avatar_label = _UserAvatarLabel(item.username, user_label, self)

        info_widget = QtWidgets.QWidget(self)
        info_layout = AYVBoxLayout(info_widget, margin=0, spacing=2)
        info_layout.addWidget(
            AYLabel(user_label, bold=True, parent=info_widget), 0
        )
        if item.workfile:
            info_layout.addWidget(
                AYLabel(item.workfile, parent=info_widget), 0
            )
        source_label = self._get_source_label(item)
        if source_label:
            info_layout.addWidget(
                AYLabel(source_label, dim=True, parent=info_widget), 0
            )
        info_layout.addStretch(1)

        times_widget = QtWidgets.QWidget(self)
        times_layout = AYVBoxLayout(times_widget, margin=0, spacing=2)
        for label in self._get_time_labels(item, now):
            times_layout.addWidget(
                AYLabel(label, dim=True, parent=times_widget),
                0,
                QtCore.Qt.AlignRight,
            )
        times_layout.addStretch(1)

        layout = AYHBoxLayout(self, margin=0, spacing=10)
        layout.addWidget(avatar_label, 0, QtCore.Qt.AlignTop)
        layout.addWidget(info_widget, 1)
        layout.addSpacing(20)
        layout.addWidget(times_widget, 0)

    @staticmethod
    def _get_source_label(item: TaskUsageItem) -> str:
        parts = []
        if item.host_name:
            parts.append(item.host_name)
        if item.machine:
            parts.append(item.machine)
        return " on ".join(parts)

    @staticmethod
    def _get_time_labels(
        item: TaskUsageItem, now: datetime.datetime
    ) -> list[str]:
        labels = []
        opened_at = item.get_opened_at()
        if opened_at is not None:
            labels.append(f"Opened {get_time_ago_label(opened_at, now)}")

        # Session is updated when a workfile is opened or saved
        updated_at = item.get_updated_at()
        if updated_at is not None and (
            opened_at is None
            or updated_at - opened_at >= MIN_SAVED_DIFFERENCE
        ):
            labels.append(f"Last saved {get_time_ago_label(updated_at, now)}")
        return labels


class TaskInUseDialog(QtWidgets.QDialog):
    """Notify user that other users are working on a task.

    Dialog is accepted if user wants to work on the task anyway.

    Args:
        items (list[TaskUsageItem]): Sessions of other users working on
            the task.
        full_names (Optional[dict[str, str]]): Full names of users by
            username. Username is shown for users without a full name.
        parent (Optional[QtWidgets.QWidget]): Parent widget.
        notice_only (bool): Only inform the user, without the option to
            cancel. Used when the task is already in use by the user.
        confirm_label (str): Label of the button to continue.

    """
    def __init__(
        self,
        items: list[TaskUsageItem],
        full_names: dict[str, str] | None = None,
        parent: QtWidgets.QWidget | None = None,
        notice_only: bool = False,
        confirm_label: str = "Open anyway",
    ):
        super().__init__(parent)
        self.setWindowTitle("Task is in use")
        self.setWindowIcon(QtGui.QIcon(get_app_icon_path()))

        if full_names is None:
            full_names = {}

        header_label = AYLabel(
            "Somebody else is already working on this task.", parent=self
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        items_widget = QtWidgets.QWidget(self)
        items_layout = AYVBoxLayout(items_widget, margin=0, spacing=14)
        for item in items:
            items_layout.addWidget(
                _SessionWidget(
                    item, full_names.get(item.username), now, items_widget
                ),
                0,
            )

        question_label = AYLabel(
            "Do you want to work on the task anyway?", parent=self
        )
        question_label.setVisible(not notice_only)

        btns_widget = QtWidgets.QWidget(self)

        cancel_btn = AYButton(
            "Cancel", variant=AYButton.Variants.Tertiary,
            parent=btns_widget,
        )
        confirm_btn = AYButton(
            confirm_label, variant=AYButton.Variants.Danger,
            parent=btns_widget,
        )
        if notice_only:
            cancel_btn.setVisible(False)
            confirm_btn.setVisible(False)
        ok_btn = AYButton(
            "OK", variant=AYButton.Variants.Surface, parent=btns_widget
        )
        ok_btn.setVisible(notice_only)

        btns_layout = AYHBoxLayout(btns_widget, margin=0, spacing=10)
        btns_layout.addStretch(1)
        btns_layout.addWidget(cancel_btn, 0)
        btns_layout.addWidget(confirm_btn, 0)
        btns_layout.addWidget(ok_btn, 0)

        main_layout = AYVBoxLayout(self, margin=15, spacing=14)
        main_layout.addWidget(header_label, 0)
        main_layout.addWidget(items_widget, 0)
        main_layout.addWidget(question_label, 0)
        main_layout.addStretch(1)
        main_layout.addWidget(btns_widget, 0)

        cancel_btn.clicked.connect(self.reject)
        confirm_btn.clicked.connect(self.accept)
        ok_btn.clicked.connect(self.accept)

        self.setMinimumWidth(420)

    def showEvent(self, event):
        super().showEvent(event)

        self.setStyleSheet(load_stylesheet())


# Keep reference to the shown notice
_notice_dialog: TaskInUseDialog | None = None


def show_task_in_use_notice(
    items: list[TaskUsageItem],
    full_names: dict[str, str] | None = None,
    delay: int = 1000,
) -> None:
    """Inform user that other users are working on the current task.

    The dialog is not modal and is shown when the Qt event loop is free,
    so it does not block startup of the application. Nothing happens if
    Qt application is not available.

    Args:
        items (list[TaskUsageItem]): Sessions of other users working on
            the task.
        full_names (Optional[dict[str, str]]): Full names of users by
            username.
        delay (int): Delay in milliseconds before the dialog is shown.

    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    def _show():
        global _notice_dialog

        if _notice_dialog is not None:
            _notice_dialog.close()
        dialog = TaskInUseDialog(items, full_names, notice_only=True)
        dialog.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        _notice_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    QtCore.QTimer.singleShot(delay, _show)
