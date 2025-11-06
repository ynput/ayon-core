import uuid
from typing import Any, Optional

from qtpy import QtCore, QtWidgets

from ayon_core.style import load_stylesheet
from ayon_core.tools.common_models import UserItem
from ayon_core.tools.utils.lib import generate_user_avatar
from ayon_core.tools.utils import (
    BaseClickableFrame,
    PlaceholderLineEdit,
    get_qt_icon,
    get_qt_app,
    PixmapLabel,
)


class FilterType(Enum):
    NO_MATCH = 0
    MATCH = 1
    FULL_MATCH = 2


class UserValueItemButton(BaseClickableFrame):
    confirmed = QtCore.Signal(str)

    def __init__(
        self,
        widget_id: str,
        item: UserItem,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)

        icon = generate_user_avatar(item)
        icon_widget = PixmapLabel(icon, self)

        title_widget = QtWidgets.QLabel(item.full_name, self)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(icon_widget, 0)
        main_layout.addWidget(title_widget, 1)

        self._icon_widget = icon_widget
        self._title_widget = title_widget
        self._main_layout = main_layout
        self._selected = False
        self._filtered = False
        self._item = item
        self._widget_id = widget_id

    def is_filtered(self) -> bool:
        return self._filtered

    def set_filtered(self, filtered: bool) -> None:
        if self._filtered is filtered:
            return
        self._filtered = filtered
        self.setVisible(not filtered)

    def check_filter(self, filter_text) -> FilterType:
        if not filter_text:
            return FilterType.MATCH
        if filter_text == self._item.username:
            return FilterType.FULL_MATCH
        if (
            filter_text in self._item.username
            or filter_text in self._item.full_name
        ):
            return FilterType.MATCH
        return FilterType.NO_MATCH

    def get_value(self) -> str:
        return self._item.username

    def set_selected(self, selected: bool) -> None:
        """Set the selection state of the widget."""
        if self._selected == selected:
            return
        self._selected = selected
        self._update_style()

    def _update_style(self):
        self.setProperty("selected", "1" if self._selected else "")
        self.style().polish(self)

    def is_selected(self) -> bool:
        return self._selected

    def _mouse_release_callback(self) -> None:
        """Handle mouse release event to emit filter request."""
        self.confirmed.emit(self._widget_id)


class ValueItemsView(QtWidgets.QWidget):
    count_changed = QtCore.Signal()
    value_confirmed = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setObjectName("ScrollArea")
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        srcoll_viewport = scroll_area.viewport()
        srcoll_viewport.setContentsMargins(0, 0, 0, 0)
        scroll_area.setWidgetResizable(True)
        # Change minimum height of scroll area
        scroll_area.setMinimumHeight(20)

        content_widget = QtWidgets.QWidget(scroll_area)
        content_widget.setObjectName("ContentWidget")

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        scroll_area.setWidget(content_widget)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area, 1)

        self._scroll_area = scroll_area
        self._content_widget = content_widget
        self._content_layout = content_layout
        self._last_selected_widget = None
        self._widgets_by_id = {}
        self._filter_text = ""
        self._filtered_ids = set()

    def get_ideal_size_hint(self) -> QtCore.QSize:
        size_hint = self._content_widget.sizeHint()
        height = 0
        rows = min(5, self._content_layout.count())
        for row in range(rows):
            item = self._content_layout.itemAt(row)
            height += item.sizeHint().height()

        return QtCore.QSize(size_hint.width() + 10, height)

    def get_value(self) -> Optional[str]:
        """Get the value from the items view."""
        if self._last_selected_widget is not None:
            return self._last_selected_widget.get_value()
        return None

    def go_up(self):
        prev_widget = None
        for idx in range(self._content_layout.count()):
            item = self._content_layout.itemAt(idx)
            widget = item.widget()
            if widget is self._last_selected_widget:
                break
            if not widget.is_filtered():
                prev_widget = widget

        if prev_widget is None:
            return

        self._last_selected_widget.set_selected(False)
        prev_widget.set_selected(True)
        self._last_selected_widget = prev_widget
        pos = prev_widget.pos()
        self._scroll_area.ensureVisible(pos.x(), pos.y())

    def go_down(self):
        next_widget = None
        current_found = False
        for idx in range(self._content_layout.count()):
            item = self._content_layout.itemAt(idx)
            widget = item.widget()
            if current_found:
                if widget.is_filtered():
                    continue
                next_widget = widget
                break

            if widget is self._last_selected_widget:
                current_found = True

        if next_widget is None:
            return

        self._last_selected_widget.set_selected(False)
        next_widget.set_selected(True)
        self._last_selected_widget = next_widget
        pos = next_widget.pos()
        self._scroll_area.ensureVisible(pos.x(), pos.y())

    def set_items(self, items: list[UserItem]) -> None:
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)
                widget.deleteLater()

        self._widgets_by_id = {}
        self._last_selected_widget = None
        for item in items:
            widget_id = item.username

            widget = UserValueItemButton(
                widget_id,
                item,
                self,
            )
            widget.confirmed.connect(self._on_item_clicked)
            if self._last_selected_widget is None:
                widget.set_selected(True)
                self._last_selected_widget = widget

            self._widgets_by_id[widget_id] = widget
            self._content_layout.addWidget(widget, 0)

        if self._content_layout.count() == 0:
            empty_label = QtWidgets.QLabel(
                "No items to select from...", self
            )
            self._content_layout.addWidget(empty_label, 0)

        # Filter items
        self.set_filter(self._filter_text)

    def set_filter(self, text):
        self._filter_text = text
        old_items_count = self.get_visible_items_count()
        text_l = text.lower()
        filtered_ids = set()
        exact_match = False
        use_first_widget = True
        first_visible_widget = None
        for widget_id, widget in self._widgets_by_id.items():
            filter_output = widget.check_filter(text)
            if filter_output == FilterType.FULL_MATCH:
                exact_match = True

            filter_matches = filter_output != FilterType.NO_MATCH
            if filter_matches:
                if first_visible_widget is None:
                    first_visible_widget = widget
                filtered_ids.add(widget_id)

            widget.set_filtered(filter_output == FilterType.NO_MATCH)
            if widget is self._last_selected_widget and filter_matches:
                use_first_widget = False

        # There is one exact match, can stay hidden
        if exact_match and len(filtered_ids) == 1:
            first_visible_widget.set_filtered(True)
            use_first_widget = False
            filtered_ids = set()

        if use_first_widget:
            if self._last_selected_widget is not None:
                self._last_selected_widget.set_selected(False)

            self._last_selected_widget = first_visible_widget
            if first_visible_widget is not None:
                first_visible_widget.set_selected(True)

        self._filtered_ids = filtered_ids
        if len(filtered_ids) != old_items_count:
            self.count_changed.emit()

    def get_visible_items_count(self):
        return len(self._filtered_ids)

    def _on_item_clicked(self, widget_id):
        widget = self._widgets_by_id.get(widget_id)
        if widget is None:
            return

        self.value_confirmed.emit(widget.get_value())


class FloatingHintWidget(QtWidgets.QWidget):
    confirmed_value = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        top_label = QtWidgets.QLabel("@ Users", self)
        top_label.setAlignment(QtCore.Qt.AlignCenter)
        top_label.setObjectName("FloatingHintLabel")

        border_frame = QtWidgets.QFrame(self)
        border_frame.setObjectName("BorderFrame")

        view = ValueItemsView(self)

        border_layout = QtWidgets.QVBoxLayout(border_frame)
        border_layout.setContentsMargins(2, 0, 2, 2)
        border_layout.addWidget(view, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top_label, 0)
        layout.addWidget(border_frame, 0)

        view.count_changed.connect(self._on_count_change)
        view.value_confirmed.connect(self._on_value_confirm)

        self._global_pos = QtCore.QPoint(0, 0)
        self._filter_value = None

        self._top_label = top_label
        self._view = view

    def confirm_value(self):
        self._confirm_value(self._view.get_value())

    def go_up(self):
        self._view.go_up()

    def go_down(self):
        self._view.go_down()

    def set_items(self, items):
        self._view.set_items(items)

    def set_pos(self, pos):
        self._global_pos = pos
        self._update_pos()

    def clear_filter(self):
        self._view.set_filter("")
        self.setVisible(False)
        self._update_size()

    def set_filter(self, text):
        self._view.set_filter(text)
        visible_items = self._view.get_visible_items_count()
        if visible_items == 0:
            self.setVisible(False)
        else:
            self.setVisible(True)
            self._update_size()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_size()

    def _update_pos(self):
        if not self.isVisible():
            return
        pos = QtCore.QPoint(self._global_pos)
        geo = self.geometry()
        pos.setY(pos.y() - (geo.height() + 2))
        self.move(pos)

    def _update_size(self):
        label_size = self._top_label.sizeHint()
        view_size = self._view.get_ideal_size_hint()
        # TODO how to get width?
        m = self.layout().contentsMargins()
        width = max(view_size.width(), label_size.width())
        width += m.left() + m.right()
        height = view_size.height() + label_size.height()
        height += m.top() + m.bottom()
        self.resize(width, height)
        self._update_pos()

    def _on_count_change(self):
        self._update_size()

    def _on_value_confirm(self, value):
        self._confirm_value(value)

    def _confirm_value(self, value):
        if value is None:
            return
        self.confirmed_value.emit(value)


class CommentInput(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        text_input = PlaceholderLineEdit(self)
        text_input.setObjectName("PublishCommentInput")
        text_input.setPlaceholderText("Attach a comment to your publish")

        floating_hints_widget = FloatingHintWidget(self)

        text_input.cursorPositionChanged.connect(self._pos_changed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_input, 1)

        floating_hints_widget.confirmed_value.connect(self._on_confirm_value)

        self._text_input = text_input
        self._floating_hints_widget = floating_hints_widget

        self._window_obj = None

    def get_comment(self) -> str:
        return self._text_input.text()

    def set_comment(self, comment: str) -> None:
        self._text_input.setText(comment)

    def set_valid(self, valid: bool) -> None:
        # Reset style
        if valid:
            self._text_input.setStyleSheet("")
            return
        self._text_input.setStyleSheet("border-color: #DD2020")
        # Set focus so user can start typing and is pointed towards the field
        self._text_input.setFocus()
        self._text_input.setCursorPosition(
            len(self.get_comment())
        )

    def set_user_items(self, items: list[UserItem]):
        self._floating_hints_widget.set_items(items)

    def eventFilter(self, obj, event):
        if obj is self._window_obj and event.type() == QtCore.QEvent.Move:
            self._update_floating_pos()
        return False

    def showEvent(self, event):
        super().showEvent(event)
        self._register_window_event_filter()
        self._update_floating_pos()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_floating_pos()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self._floating_hints_widget.setVisible(False)
            event.accept()
            return

        if self._floating_hints_widget.isVisible():
            if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
                self._floating_hints_widget.confirm_value()
                event.accept()
                return

            if event.key() == QtCore.Qt.Key_Up:
                self._floating_hints_widget.go_up()
                event.accept()
                return

            if event.key() == QtCore.Qt.Key_Down:
                self._floating_hints_widget.go_down()
                event.accept()
                return

        super().keyPressEvent(event)

    def _register_window_event_filter(self):
        window = self.window()
        if window is None or window is self._window_obj:
            return

        if self._window_obj is not None:
            self.removeEventFilter(self._window_obj)

        self._window_obj = window
        self._window_obj.installEventFilter(self)

    def _update_floating_pos(self):
        self._floating_hints_widget.set_pos(
            self.mapToGlobal(QtCore.QPoint(0, 0))
        )

    def _pos_changed(self, _old_pos, pos):
        text = self._text_input.text()
        self._update_hints(pos, text)

    def _update_hints(self, pos, text):
        if pos == 0:
            self._floating_hints_widget.clear_filter()
            return

        before_part = text[:pos].split(" ")[-1]
        after_part = text[pos:].split(" ")[0]
        lim_text = before_part + after_part
        # NOTE should we support version and task?
        if not lim_text.startswith("@"):
            self._floating_hints_widget.clear_filter()
            return

        self._floating_hints_widget.set_filter(lim_text.lstrip("@"))

    def _on_confirm_value(self, value):
        text = self._text_input.text()
        pos = self._text_input.cursorPosition()

        before_parts = text[:pos].split(" ")
        before_part = before_parts.pop(-1)
        if not before_part.startswith("@"):
            return
        after_parts = text[pos:].split(" ")
        _after_part = after_parts.pop(0)

        before_parts.append(f"@{value}")
        beginning = " ".join(before_parts)

        after_parts.insert(0, beginning)
        full_text = " ".join(after_parts)
        self._text_input.setText(full_text)
        self._text_input.setCursorPosition(len(beginning))
        self._floating_hints_widget.setVisible(False)


