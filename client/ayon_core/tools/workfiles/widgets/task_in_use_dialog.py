from __future__ import annotations

import datetime
import typing

from qtpy import QtWidgets, QtGui

from ayon_core.style import load_stylesheet, get_app_icon_path
from ayon_core.tools.utils.delegates import pretty_date
from ayon_core.ui.components import (
    AYButton,
    AYLabel,
    AYHBoxLayout,
    AYVBoxLayout
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.workfile.task_usage import TaskUsageItem
    from ayon_core.tools.common_models import UserItem


class TaskInUseDialog(QtWidgets.QDialog):
    """Notify user that other users are working on a task.

    Dialog is accepted if user wants to work on the task anyway.

    Args:
        items (list[TaskUsageItem]): Sessions of other users working on
            the task.
        user_items_by_name (Optional[dict[str, UserItem]]): User items used
            to show full names of the users.
        parent (Optional[QtWidgets.QWidget]): Parent widget.

    """
    def __init__(
        self,
        items: list[TaskUsageItem],
        user_items_by_name: dict[str, UserItem] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Task is in use")
        self.setWindowIcon(QtGui.QIcon(get_app_icon_path()))

        if user_items_by_name is None:
            user_items_by_name = {}

        header_label = AYLabel(
            "Somebody else is already working on this task.", parent=self
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        items_widget = QtWidgets.QWidget(self)
        items_layout = AYVBoxLayout(items_widget, margin=0, spacing=10)
        for item in items:
            title, details = self._get_item_labels(
                item, user_items_by_name, now
            )
            item_widget = QtWidgets.QWidget(items_widget)
            title_label = AYLabel(
                title, icon="person", bold=True, parent=item_widget
            )
            details_label = AYLabel(details, dim=True, parent=item_widget)
            item_layout = AYVBoxLayout(item_widget, margin=0, spacing=2)
            item_layout.addWidget(title_label, 0)
            item_layout.addWidget(details_label, 0)
            items_layout.addWidget(item_widget, 0)

        question_label = AYLabel(
            "Do you want to work on the task anyway?", parent=self
        )

        btns_widget = QtWidgets.QWidget(self)

        cancel_btn = AYButton(
            "Cancel", variant=AYButton.Variants.Tertiary,
            parent=btns_widget,
        )
        confirm_btn = AYButton(
            "Open anyway", variant=AYButton.Variants.Danger,
            parent=btns_widget,
        )

        btns_layout = AYHBoxLayout(btns_widget, margin=0, spacing=10)
        btns_layout.addStretch(1)
        btns_layout.addWidget(cancel_btn, 0)
        btns_layout.addWidget(confirm_btn, 0)

        main_layout = AYVBoxLayout(self, margin=15, spacing=12)
        main_layout.addWidget(header_label, 0)
        main_layout.addWidget(items_widget, 0)
        main_layout.addWidget(question_label, 0)
        main_layout.addStretch(1)
        main_layout.addSpacing(10)
        main_layout.addWidget(btns_widget, 0)

        cancel_btn.clicked.connect(self.reject)
        confirm_btn.clicked.connect(self.accept)

        self.setMinimumWidth(460)

    def showEvent(self, event):
        super().showEvent(event)

        self.setStyleSheet(load_stylesheet())

    @staticmethod
    def _get_item_labels(
        item: TaskUsageItem,
        user_items_by_name: dict[str, UserItem],
        now: datetime.datetime,
    ) -> tuple[str, str]:
        """Prepare labels of a session.

        Returns:
            tuple[str, str]: Title with user and workfile, and details
                about the session.

        """
        title = item.username
        user_item = user_items_by_name.get(item.username)
        if user_item is not None and user_item.full_name:
            title = user_item.full_name
        if item.workfile:
            title = f"{title} in {item.workfile}"

        details = []
        if item.host_name:
            details.append(item.host_name)
        if item.machine:
            details.append(f"on {item.machine}")

        opened_at = item.get_opened_at()
        if opened_at is not None:
            opened = pretty_date(opened_at.astimezone(), now)
            details.append(f"opened {opened}")

        updated_at = item.get_updated_at()
        if updated_at is not None:
            updated = pretty_date(updated_at.astimezone(), now)
            details.append(f"last activity {updated}")

        return title, ", ".join(details)
