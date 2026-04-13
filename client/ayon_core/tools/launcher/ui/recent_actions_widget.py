import html

import qtawesome
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import (
    SquareButton,
    get_qt_icon,
)
from ayon_core.tools.utils.delegates import pretty_timestamp

RECORD_ID_ROLE = QtCore.Qt.UserRole + 1
_QWIDGETSIZE_MAX = (1 << 24) - 1

_TRANSPARENT_ICON_DEF = {"type": "transparent", "size": 256}
_PLAY_ICON_DEF = {
    "type": "material-symbols",
    "name": "play_arrow",
}


def _get_play_icon():
    return get_qt_icon(_PLAY_ICON_DEF)


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
    """Single row in the recent-actions popup.

    Emits navigate_requested / replay_requested with the record_id.
    Row click navigates to the stored context; the side button re-runs the
    action.  Highlights the entire row on hover so it behaves like a menu
    entry.
    """

    navigate_requested = QtCore.Signal(str)
    replay_requested = QtCore.Signal(str)

    _play_icon = None

    @classmethod
    def _get_play_icon(cls):
        if cls._play_icon is None:
            cls._play_icon = _get_play_icon()
        return cls._play_icon

    def __init__(
        self,
        record_id,
        icon,
        label,
        breadcrumb,
        timestamp_label,
        parent=None,
    ):
        super().__init__(parent)
        self._record_id = record_id
        self._hovered = False

        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)

        tooltip_lines = []
        if breadcrumb:
            tooltip_lines.append(f"Go to context:\n{breadcrumb}")
        if timestamp_label:
            tooltip_lines.append(f"Triggered: {timestamp_label}")
        if tooltip_lines:
            self.setToolTip("\n\n".join(tooltip_lines))

        icon_label = QtWidgets.QLabel(self)
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(
            QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter
        )
        if icon is not None:
            pixmap = icon.pixmap(28, 28)
            icon_label.setPixmap(pixmap)

        text_label = QtWidgets.QLabel(self)
        text_label.setTextFormat(QtCore.Qt.RichText)
        text_label.setText(f"<b>{html.escape(label)}</b>")
        text_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Breadcrumb line – shown only when context is available
        breadcrumb_label = QtWidgets.QLabel(breadcrumb, self)
        breadcrumb_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        breadcrumb_label.setObjectName("RecentActionBreadcrumb")
        breadcrumb_font = breadcrumb_label.font()
        breadcrumb_font.setPointSizeF(breadcrumb_font.pointSizeF() * 0.82)
        breadcrumb_label.setFont(breadcrumb_font)
        breadcrumb_label.setVisible(bool(breadcrumb))

        timestamp_widget = QtWidgets.QLabel(timestamp_label, self)
        timestamp_widget.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        timestamp_widget.setObjectName("RecentActionTimestamp")
        timestamp_font = timestamp_widget.font()
        timestamp_font.setPointSizeF(timestamp_font.pointSizeF() * 0.74)
        timestamp_widget.setFont(timestamp_font)
        timestamp_widget.setVisible(bool(timestamp_label))
        timestamp_widget.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )

        top_row_layout = QtWidgets.QHBoxLayout()
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(8)
        top_row_layout.addWidget(text_label, 1)
        top_row_layout.addWidget(timestamp_widget, 0, QtCore.Qt.AlignVCenter)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.addLayout(top_row_layout)
        text_layout.addWidget(breadcrumb_label)

        play_btn = QtWidgets.QPushButton(self)
        play_btn.setIcon(self._get_play_icon())
        play_btn.setIconSize(QtCore.QSize(18, 18))
        play_btn.setToolTip(
            f"Re-run action: {label}"
        )
        play_btn.setFlat(True)
        play_btn.setFixedSize(28, 28)
        play_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed,
        )
        play_btn.setCursor(QtCore.Qt.PointingHandCursor)
        play_btn.setObjectName("RecentPlayBtn")

        row_layout = QtWidgets.QHBoxLayout(self)
        row_layout.setContentsMargins(6, 3, 4, 3)
        row_layout.setSpacing(4)
        row_layout.addWidget(icon_label, 0, QtCore.Qt.AlignVCenter)
        row_layout.addLayout(text_layout, 1)
        row_layout.addSpacing(6)
        row_layout.addWidget(play_btn, 0, QtCore.Qt.AlignTop)

        self._icon_label = icon_label
        self._text_label = text_label
        self._breadcrumb_label = breadcrumb_label
        self._timestamp_label = timestamp_widget
        self._play_btn = play_btn

        play_btn.clicked.connect(self._on_play_clicked)

        self.setObjectName("RecentActionRow")

    # ------------------------------------------------------------------
    # Hover highlight – paint a subtle selection background on hover

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hovered:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
            color = self.palette().color(QtGui.QPalette.Highlight)
            color.setAlpha(60)
            painter.fillRect(self.rect(), color)
            painter.end()

    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())
            if child is not self._play_btn and not isinstance(
                child, QtWidgets.QPushButton
            ):
                self.navigate_requested.emit(self._record_id)
        super().mousePressEvent(event)

    def _on_play_clicked(self):
        self.replay_requested.emit(self._record_id)


class RecentActionsPopup(QtWidgets.QFrame):
    """Popup window listing recent actions.

    Appears as a floating panel positioned near the trigger button.
    Closes automatically when focus is lost (Qt.Popup behaviour).
    """

    def __init__(self, controller, parent=None):
        super().__init__(
            parent,
            QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint,
        )
        self.setObjectName("RecentActionsPopup")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        self._controller = controller
        self._rows = []

        # Title bar
        title_label = QtWidgets.QLabel("Recent Actions", self)
        title_label.setObjectName("RecentActionsTitle")
        font = title_label.font()
        font.setBold(True)
        title_label.setFont(font)
        title_label.setContentsMargins(8, 6, 8, 4)

        separator = QtWidgets.QFrame(self)
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setObjectName("RecentActionsSeparator")

        # Scroll area for rows
        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setObjectName("RecentActionsScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        rows_container = QtWidgets.QWidget(scroll_area)
        rows_container.setObjectName("RecentActionsContainer")
        rows_layout = QtWidgets.QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(4, 4, 4, 4)
        rows_layout.setSpacing(2)

        empty_label = QtWidgets.QLabel(
            "No recent actions yet.", rows_container
        )
        empty_label.setObjectName("RecentActionsEmpty")
        empty_label.setAlignment(QtCore.Qt.AlignCenter)
        empty_label.setContentsMargins(12, 8, 12, 8)
        rows_layout.addWidget(empty_label)
        rows_layout.addStretch(1)

        scroll_area.setWidget(rows_container)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(title_label, 0)
        main_layout.addWidget(separator, 0)
        main_layout.addWidget(scroll_area, 1)

        self._scroll_area = scroll_area
        self._rows_container = rows_container
        self._rows_layout = rows_layout
        self._empty_label = empty_label

        controller.register_event_callback(
            "recent_actions.changed",
            self._on_recent_actions_changed,
        )

    # ------------------------------------------------------------------
    # Public API

    def refresh(self):
        """Re-fetch recent items from the controller and rebuild rows."""
        items = self._controller.get_recent_action_items()
        self._rebuild_rows(items)

    def show_near(self, widget):
        """Position the popup near *widget* and show it.

        The right edge of the popup aligns with the right edge of *widget*.
        The popup expands to fit all rows when space allows, and scrolls when
        content exceeds available vertical screen space.
        """
        self.refresh()

        min_width = max(widget.topLevelWidget().width() // 2, 320)
        self.setMinimumWidth(min_width)

        # Determine available vertical space below the button so we can cap
        # the scroll area *before* adjustSize() computes the popup height.
        # This ensures adjustSize() produces the correct final dimensions and
        # no scrollbar appears when the content fits.
        btn_bottom_right = widget.mapToGlobal(
            QtCore.QPoint(widget.width(), widget.height())
        )
        screen = (
            QtWidgets.QApplication.screenAt(btn_bottom_right)
            or QtWidgets.QApplication.primaryScreen()
        )
        if screen is not None:
            avail = screen.availableGeometry()
            available_h = avail.bottom() - btn_bottom_right.y() - 2
            # Give the scroll area the full available height; adjustSize()
            # will shrink the popup to its actual content if smaller.
            self._scroll_area.setMaximumHeight(max(50, available_h))
        else:
            avail = None

        self.adjustSize()

        popup_w = self.width()
        popup_h = self.height()
        x = btn_bottom_right.x() - popup_w
        y = btn_bottom_right.y() + 2

        # Clamp horizontal position to keep popup on screen.
        if avail is not None:
            x = max(avail.left(), min(x, avail.right() - popup_w))
            y = max(avail.top(), min(y, avail.bottom() - popup_h))

        self.move(x, y)
        self.show()

    # ------------------------------------------------------------------
    # Internal helpers

    def _rebuild_rows(self, items):
        # Remove existing rows
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.setVisible(False)
            row.deleteLater()
        self._rows = []

        # Remove stretch placeholder if present
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        has_items = bool(items)
        self._empty_label.setVisible(not has_items)

        transparent_icon = get_qt_icon(_TRANSPARENT_ICON_DEF)
        for action_item in items:
            icon = _get_recent_action_icon(
                action_item,
                self._controller,
                transparent_icon,
            )
            breadcrumb = _build_breadcrumb(action_item, self._controller)
            timestamp_label = pretty_timestamp(action_item.timestamp) or ""
            row = _RecentActionRow(
                action_item.record_id,
                icon,
                action_item.label,
                breadcrumb,
                timestamp_label,
                self._rows_container,
            )
            row.navigate_requested.connect(self._on_navigate)
            row.replay_requested.connect(self._on_replay)
            self._rows_layout.addWidget(row)
            self._rows.append(row)

        # Keep stretch at bottom
        self._rows_layout.addStretch(1)

        # Reset any previously applied height cap so show_near() can size
        # the popup against actual available screen space instead of a fixed
        # row-height estimate.
        self._scroll_area.setMinimumHeight(0)
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


class RecentActionsButton(SquareButton):
    """Icon-only button that shows/hides the recent-actions popup."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)

        icon = qtawesome.icon("fa.history", color="white")
        self.setIcon(icon)
        self.setToolTip("Recent Actions")
        self.setObjectName("RecentActionsButton")

        self._popup = RecentActionsPopup(controller, self)

        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.show_near(self)
