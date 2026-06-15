from qtpy import QtWidgets, QtCore

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.delegates import pretty_timestamp
from ayon_core.ui.components import AYButton, AYFrame, AYLabel
from ayon_core.ui.components.dropdown import AYDropdownPopup
from ayon_core.ui.components.layouts import AYVBoxLayout, AYHBoxLayout
from ayon_core.ui.components.scroll_area import AYScrollArea

_TRANSPARENT_ICON_DEF = {"type": "transparent", "size": 256}
RECORD_ID_ROLE = QtCore.Qt.UserRole + 1
_QWIDGETSIZE_MAX = (1 << 24) - 1


def _build_breadcrumb(action_item, controller=None) -> str:
    """Build a rich breadcrumb string: project › folder_path › task › workfile.

    Falls back gracefully when context pieces are unavailable or lookups fail.
    """
    parts = []

    project_name = action_item.project_name or ""
    if project_name:
        parts.append(project_name)

    # Folder path – needs a controller lookup; best-effort only.
    if controller is not None and project_name and action_item.folder_id:
        try:
            folder_entity = controller.get_folder_entity(
                project_name, action_item.folder_id
            )
            if folder_entity:
                folder_path = folder_entity.get("path") or folder_entity.get(
                    "name"
                )
                if folder_path:
                    parts.append(folder_path)
        except Exception:
            pass

    task_name = action_item.task_name
    if (
        not task_name
        and controller is not None
        and project_name
        and action_item.task_id
    ):
        try:
            task_entity = controller.get_task_entity(
                project_name, action_item.task_id
            )
            task_name = (task_entity or {}).get("name")
        except Exception:
            pass

    if task_name:
        parts.append(task_name)

    # Workfile filename – look up by workfile_id inside the task's items.
    if (
        controller is not None
        and project_name
        and action_item.task_id
        and action_item.workfile_id
    ):
        try:
            workfile_items = controller.get_workfile_items(
                project_name, action_item.task_id
            )
            for wf in workfile_items:
                if wf.workfile_id == action_item.workfile_id:
                    if wf.filename:
                        parts.append(wf.filename)
                    break
        except Exception:
            pass

    return " \u203a ".join(parts)


def _get_recent_action_icon(action_item, controller, fallback_icon):
    if controller is None:
        return fallback_icon

    try:
        action_items = controller.get_action_items(
            action_item.project_name,
            action_item.folder_id,
            action_item.task_id,
            action_item.workfile_id,
        )
    except Exception:
        return fallback_icon

    for candidate in action_items:
        if candidate.action_type != action_item.action_type:
            continue
        if candidate.identifier != action_item.identifier:
            continue
        if action_item.action_type == "webaction" and (
            candidate.addon_name != action_item.addon_name
            or candidate.addon_version != action_item.addon_version
        ):
            continue

        icon_def = candidate.icon
        if not icon_def:
            return fallback_icon
        try:
            return get_qt_icon(icon_def)
        except Exception:
            return fallback_icon

    return fallback_icon


class _RecentActionRow(QtWidgets.QWidget):
    """Single row: icon + label/breadcrumb + timestamp + replay button."""

    navigate_requested = QtCore.Signal(str)
    replay_requested = QtCore.Signal(str)

    def __init__(self, record_id, icon, label, breadcrumb, timestamp_label, parent=None):
        super().__init__(parent)
        self._record_id = record_id
        self.setCursor(QtCore.Qt.PointingHandCursor)

        tooltip_lines = []
        if breadcrumb:
            tooltip_lines.append(f"Go to context:\n{breadcrumb}")
        if timestamp_label:
            tooltip_lines.append(f"Triggered: {timestamp_label}")
        if tooltip_lines:
            self.setToolTip("\n\n".join(tooltip_lines))

        icon_label = QtWidgets.QLabel(self)
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        if icon is not None:
            icon_label.setPixmap(icon.pixmap(28, 28))

        text_label = AYLabel(label, bold=True, parent=self)
        text_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        breadcrumb_label = AYLabel(
            breadcrumb, dim=True, rel_text_size=-2,
            elide_mode=QtCore.Qt.ElideMiddle, parent=self,
        )
        breadcrumb_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        breadcrumb_label.setObjectName("RecentActionBreadcrumb")
        breadcrumb_label.setVisible(bool(breadcrumb))

        timestamp_widget = AYLabel(
            timestamp_label, dim=True, rel_text_size=-2, parent=self,
        )
        timestamp_widget.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        timestamp_widget.setObjectName("RecentActionTimestamp")
        timestamp_widget.setVisible(bool(timestamp_label))

        play_btn = AYButton(
            variant=AYButton.Variants.Surface,
            icon="play_arrow", icon_size=18,
            tooltip=f"Re-run action: {label}",
            parent=self,
        )
        play_btn.setCursor(QtCore.Qt.PointingHandCursor)
        play_btn.setObjectName("RecentPlayBtn")

        top_row = AYHBoxLayout(margin=0, spacing=8)
        top_row.addWidget(text_label, 1)
        top_row.addWidget(timestamp_widget, 0, QtCore.Qt.AlignVCenter)

        text_col = AYVBoxLayout(margin=0, spacing=1)
        text_col.addLayout(top_row)
        text_col.addWidget(breadcrumb_label)

        row_layout = AYHBoxLayout(self, margin=4, spacing=4)
        row_layout.addWidget(icon_label, 0, QtCore.Qt.AlignVCenter)
        row_layout.addLayout(text_col, 1)
        row_layout.addWidget(play_btn, 0)

        self._play_btn = play_btn
        play_btn.clicked.connect(lambda: self.replay_requested.emit(self._record_id))
        self.setObjectName("RecentActionRow")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())
            if not isinstance(child, QtWidgets.QPushButton):
                self.navigate_requested.emit(self._record_id)
        super().mousePressEvent(event)


class RecentActionsPopup(AYDropdownPopup):
    """Popup listing recent actions, anchored below the trigger button."""

    def __init__(self, controller, parent=None):
        super().__init__(parent, variant=AYDropdownPopup.Variants.Low_Framed_Thin)
        self._controller = controller
        self._rows = []

        title_label = AYLabel("Recent Actions", bold=True, parent=self)
        title_label.setObjectName("RecentActionsTitle")
        title_label.setContentsMargins(8, 6, 8, 4)

        separator = AYFrame(self)
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)

        scroll_area = AYScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        rows_container = QtWidgets.QWidget(scroll_area)
        rows_container.setObjectName("RecentActionsContainer")
        self._rows_layout = AYVBoxLayout(rows_container, margin=4, spacing=2)

        self._empty_label = AYLabel(
            "No recent actions yet.", dim=True, parent=rows_container
        )
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self._empty_label.setContentsMargins(12, 8, 12, 8)
        self._rows_layout.addWidget(self._empty_label)
        self._rows_layout.addStretch(1)

        scroll_area.setWidget(rows_container)
        self._scroll_area = scroll_area
        self._rows_container = rows_container

        main_layout = AYVBoxLayout(self, margin=0, spacing=0)
        main_layout.addWidget(title_label, 0)
        main_layout.addWidget(separator, 0)
        main_layout.addWidget(scroll_area, 1)

        controller.register_event_callback(
            "recent_actions.changed", self._on_recent_actions_changed
        )

    def refresh(self):
        items = self._controller.get_recent_action_items()
        self._rebuild_rows(items)

    def show_near(self, widget):
        self.refresh()
        min_width = max(widget.topLevelWidget().width() // 2, 320)
        btn_br = widget.mapToGlobal(QtCore.QPoint(widget.width(), widget.height()))
        screen = QtWidgets.QApplication.screenAt(btn_br) or QtWidgets.QApplication.primaryScreen()
        preferred_width = self.sizeHint().width()
        if screen is not None:
            avail = screen.availableGeometry()
            max_width = max(min_width, btn_br.x() - avail.left() - 2)
            self._scroll_area.setMaximumHeight(max(50, avail.bottom() - btn_br.y() - 2))
        else:
            avail = None
            max_width = max(min_width, preferred_width)
        target_w = min(max(preferred_width, min_width), max_width)
        self.setMinimumWidth(target_w)
        self.setMaximumWidth(max_width)
        self.adjustSize()
        x = btn_br.x() - target_w
        y = btn_br.y() + 2
        if avail is not None:
            x = max(avail.left(), min(x, avail.right() - target_w))
            y = max(avail.top(), min(y, avail.bottom() - self.height()))
        self.move(x, y)
        self.resize(target_w, self.height())
        self.show()

    def _rebuild_rows(self, items):
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        self._empty_label.setVisible(not bool(items))
        fallback = get_qt_icon(_TRANSPARENT_ICON_DEF)
        for action_item in items:
            icon = _get_recent_action_icon(action_item, self._controller, fallback)
            row = _RecentActionRow(
                action_item.record_id, icon, action_item.label,
                _build_breadcrumb(action_item, self._controller),
                pretty_timestamp(action_item.timestamp) or "",
                self._rows_container,
            )
            row.navigate_requested.connect(self._on_navigate)
            row.replay_requested.connect(self._on_replay)
            self._rows_layout.addWidget(row)
            self._rows.append(row)
        self._rows_layout.addStretch(1)
        self._scroll_area.setMaximumHeight(_QWIDGETSIZE_MAX)

    def _on_navigate(self, record_id):
        self._controller.apply_recent_action_context(record_id)
        self.hide()

    def _on_replay(self, record_id):
        self._controller.trigger_recent_action(record_id)
        self.hide()

    def _on_recent_actions_changed(self, event):
        if self.isVisible():
            self.refresh()


class RecentActionsButton(AYButton):
    """Icon-only button that shows/hides the recent-actions popup."""

    def __init__(self, controller, parent=None):
        super().__init__(
            icon="history",
            variant=AYButton.Variants.Surface,
            tooltip="Recent Actions",
            parent=parent,
        )
        self.setObjectName("RecentActionsButton")
        self._popup = RecentActionsPopup(controller, self)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.show_near(self)
