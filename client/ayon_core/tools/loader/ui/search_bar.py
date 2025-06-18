import copy
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from qtpy import QtCore, QtWidgets, QtGui

from ayon_core.style import get_objected_colors
from ayon_core.tools.utils import (
    get_qt_icon,
    SquareButton,
    BaseClickableFrame,
    PixmapLabel,
    SeparatorWidget,
)


def set_line_edit_focus(
    widget: QtWidgets.QLineEdit,
    *,
    append_text: Optional[str] = None,
    backspace: bool = False,
):
    full_text = widget.text()
    if backspace and full_text:
        full_text = full_text[:-1]

    if append_text:
        full_text += append_text
    widget.setText(full_text)
    widget.setFocus()
    widget.setCursorPosition(len(full_text))


@dataclass
class FilterDefinition:
    """Search bar definition.

    Attributes:
        name (str): Name of the definition.
        title (str): Title of the search bar.
        icon (str): Icon name for the search bar.
        placeholder (str): Placeholder text for the search bar.

    """
    name: str
    title: str
    filter_type: str
    icon: Optional[dict[str, Any]] = None
    placeholder: Optional[str] = None
    items: Optional[list[dict[str, str]]] = None


class CloseButton(SquareButton):
    """Close button for search item display widget."""
    _icon = None
    _hover_color = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.__class__._icon is None:
            self.__class__._icon = get_qt_icon({
                "type": "material-symbols",
                "name": "close",
                "color": "#FFFFFF",
            })
        if self.__class__._hover_color is None:
            color = get_objected_colors("bg-view-selection-hover")
            self.__class__._hover_color = color.get_qcolor()

        self.setIcon(self.__class__._icon)

    def paintEvent(self, event):
        """Override paint event to draw a close button."""
        painter = QtWidgets.QStylePainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        icon = self.icon()
        size = min(self.width(), self.height())
        rect = QtCore.QRect(0, 0, size, size)
        rect.adjust(2, 2, -2, -2)
        painter.setPen(QtCore.Qt.NoPen)
        bg_color = QtCore.Qt.transparent
        if option.state & QtWidgets.QStyle.State_MouseOver:
            bg_color = self._hover_color

        painter.setBrush(bg_color)
        painter.setClipRect(event.rect())
        painter.drawEllipse(rect)
        rect.adjust(2, 2, -2, -2)
        icon.paint(painter, rect)


class SearchItemDisplayWidget(BaseClickableFrame):
    """Widget displaying a set filter in the bar."""
    close_requested = QtCore.Signal(str)
    edit_requested = QtCore.Signal(str)

    def __init__(
        self,
        filter_def: FilterDefinition,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)

        self._filter_def = filter_def

        title_widget = QtWidgets.QLabel(f"{filter_def.title}:", self)

        value_wrapper = QtWidgets.QWidget(self)
        value_wrapper.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        value_widget = QtWidgets.QLabel(value_wrapper)
        value_widget.setObjectName("ValueWidget")
        value_widget.setText("")
        value_layout = QtWidgets.QVBoxLayout(value_wrapper)
        value_layout.setContentsMargins(2, 2, 2, 2)
        value_layout.addWidget(value_widget)

        close_btn = CloseButton(self)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(4, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(title_widget, 0)
        main_layout.addWidget(value_wrapper, 0)
        main_layout.addWidget(close_btn, 0)

        close_btn.clicked.connect(self._on_remove_clicked)

        self._value_wrapper = value_wrapper
        self._value_widget = value_widget
        self._value = None

    def set_value(self, value: "str | list[str]"):
        text = ""
        ellide = True
        if value is None:
            pass
        elif isinstance(value, str):
            text = value
        elif len(value) == 1:
            text = value[0]
        elif len(value) > 1:
            ellide = False
            text = f"Items: {len(value)}"

        if ellide and len(text) > 9:
            text = text[:9] + "..."

        text = " " + text + " "

        self._value = copy.deepcopy(value)
        self._value_widget.setText(text)

    def get_value(self):
        return copy.deepcopy(self._value)

    def _on_remove_clicked(self):
        self.close_requested.emit(self._filter_def.name)

    def _mouse_release_callback(self):
        self.edit_requested.emit(self._filter_def.name)


class FilterItemButton(BaseClickableFrame):
    filter_requested = QtCore.Signal(str)

    def __init__(
        self,
        filter_def: FilterDefinition,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(parent)

        self._filter_def = filter_def

        title_widget = QtWidgets.QLabel(filter_def.title, self)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(title_widget, 1)

        self._title_widget = title_widget

    def _mouse_release_callback(self):
        """Handle mouse release event to emit filter request."""
        self.filter_requested.emit(self._filter_def.name)


class FiltersPopup(QtWidgets.QWidget):
    filter_requested = QtCore.Signal(str)
    text_filter_requested = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        shadow_frame = QtWidgets.QFrame(self)
        shadow_frame.setObjectName("ShadowFrame")

        wrapper = QtWidgets.QWidget(self)
        wrapper.setObjectName("PopupWrapper")

        wraper_layout = QtWidgets.QVBoxLayout(wrapper)
        wraper_layout.setContentsMargins(5, 5, 5, 5)
        wraper_layout.setSpacing(5)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.addWidget(wrapper)

        shadow_frame.stackUnder(wrapper)

        self._shadow_frame = shadow_frame
        self._wrapper = wrapper
        self._wrapper_layout = wraper_layout
        self._preferred_width = None

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            event.accept()
            self.close()
            return

        if event.key() in (
            QtCore.Qt.Key_Backtab,
            QtCore.Qt.Key_Backspace,
        ):
            self.text_filter_requested.emit("")
            event.accept()
            return

        valid_modifiers = event.modifiers() in (
            QtCore.Qt.NoModifier,
            QtCore.Qt.ShiftModifier,
        )
        if valid_modifiers and event.key() not in (
            QtCore.Qt.Key_Escape,
            QtCore.Qt.Key_Tab,
            QtCore.Qt.Key_Return,
        ):
            text = event.text()
            if text:
                event.accept()
                self.text_filter_requested.emit(text)
                return
        super().keyPressEvent(event)

    def set_preferred_width(self, width: int):
        self._preferred_width = width

    def sizeHint(self):
        sh = super().sizeHint()
        if self._preferred_width is not None:
            sh.setWidth(self._preferred_width)
        return sh

    def set_filter_items(self, filter_items):
        while self._wrapper_layout.count() > 0:
            item = self._wrapper_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)
                widget.deleteLater()

        for item in filter_items:
            widget = FilterItemButton(item, self._wrapper)
            widget.filter_requested.connect(self.filter_requested)
            self._wrapper_layout.addWidget(widget, 0)

        if self._wrapper_layout.count() == 0:
            empty_label = QtWidgets.QLabel(
                "No filters available...", self._wrapper
            )
            self._wrapper_layout.addWidget(empty_label, 0)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_shadow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_shadow()

    def _update_shadow(self):
        geo = self.geometry()
        geo.moveTopLeft(QtCore.QPoint(0, 0))
        self._shadow_frame.setGeometry(geo)


class FilterValueItemButton(BaseClickableFrame):
    selected = QtCore.Signal(str)

    def __init__(self, widget_id, value, icon, color, parent):
        super().__init__(parent)

        title_widget = QtWidgets.QLabel(str(value), self)
        if color:
            title_widget.setStyleSheet(f"color: {color};")

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(title_widget, 1)

        self._icon_widget = None
        self._title_widget = title_widget
        self._main_layout = main_layout
        self._selected = False
        self._value = value
        self._widget_id = widget_id

        if icon:
            self.set_icon(icon)

    def set_icon(self, icon: dict[str, Any]):
        """Set the icon for the widget."""
        icon = get_qt_icon(icon)
        pixmap = icon.pixmap(64, 64)
        if self._icon_widget is None:
            self._icon_widget = PixmapLabel(pixmap, self)
            self._main_layout.insertWidget(0, self._icon_widget, 0)
        else:
            self._icon_widget.setPixmap(pixmap)

    def get_value(self):
        return self._value

    def set_selected(self, selected: bool):
        """Set the selection state of the widget."""
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", "1" if selected else "")
        self.style().polish(self)

    def is_selected(self) -> bool:
        return self._selected

    def _mouse_release_callback(self):
        """Handle mouse release event to emit filter request."""
        self.selected.emit(self._widget_id)


class FilterValueTextInput(QtWidgets.QWidget):
    back_requested = QtCore.Signal()
    value_changed = QtCore.Signal(str)
    close_requested = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Timeout is used to delay the filter focus change on 'showEvent'
        # - the focus is changed to something else if is not delayed
        filter_timeout = QtCore.QTimer(self)
        filter_timeout.setSingleShot(True)
        filter_timeout.setInterval(20)

        btns_sep = SeparatorWidget(size=1, parent=self)
        btns_widget = QtWidgets.QWidget(self)
        btns_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        text_input = QtWidgets.QLineEdit(self)

        back_btn = QtWidgets.QPushButton("Back", btns_widget)
        back_btn.setObjectName("BackButton")
        back_btn.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "arrow_back",
        }))
        confirm_btn = QtWidgets.QPushButton("Confirm", btns_widget)
        confirm_btn.setObjectName("ConfirmButton")

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addWidget(back_btn, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(confirm_btn, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(text_input, 0)
        main_layout.addWidget(btns_sep, 0)
        main_layout.addWidget(btns_widget, 0)

        filter_timeout.timeout.connect(self._on_filter_timeout)
        text_input.textChanged.connect(self.value_changed)
        text_input.returnPressed.connect(self.close_requested)
        back_btn.clicked.connect(self.back_requested)
        confirm_btn.clicked.connect(self.close_requested)

        self._filter_timeout = filter_timeout
        self._text_input = text_input

    def showEvent(self, event):
        super().showEvent(event)

        self._filter_timeout.start()

    def get_value(self) -> str:
        return self._text_input.text()

    def set_value(self, value: str):
        self._text_input.setText(value)

    def set_placeholder_text(self, placeholder_text: str):
        self._text_input.setPlaceholderText(placeholder_text)

    def set_text_filter(self, text: str):
        kwargs = {}
        if text:
            kwargs["append_text"] = text
        else:
            kwargs["backspace"] = True

        set_line_edit_focus(self._text_input, **kwargs)

    def _on_filter_timeout(self):
        set_line_edit_focus(self._text_input)


class FilterValueItemsView(QtWidgets.QWidget):
    value_changed = QtCore.Signal()
    close_requested = QtCore.Signal()
    back_requested = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        filter_input = QtWidgets.QLineEdit(self)
        filter_input.setPlaceholderText("Filter items...")

        # Timeout is used to delay the filter focus change on 'showEvent'
        # - the focus is changed to something else if is not delayed
        filter_timeout = QtCore.QTimer(self)
        filter_timeout.setSingleShot(True)
        filter_timeout.setInterval(20)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setObjectName("ScrollArea")
        srcoll_viewport = scroll_area.viewport()
        srcoll_viewport.setContentsMargins(0, 0, 0, 0)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(20)
        scroll_area.setMaximumHeight(400)

        content_widget = QtWidgets.QWidget(scroll_area)
        content_widget.setObjectName("ContentWidget")

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area.setWidget(content_widget)

        btns_sep = SeparatorWidget(size=1, parent=self)
        btns_widget = QtWidgets.QWidget(self)
        btns_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        back_btn = QtWidgets.QPushButton("Back", btns_widget)
        back_btn.setObjectName("BackButton")
        back_btn.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "arrow_back",
        }))

        select_all_btn = QtWidgets.QPushButton("Select all", btns_widget)
        clear_btn = QtWidgets.QPushButton("Clear", btns_widget)
        swap_btn = QtWidgets.QPushButton("Invert", btns_widget)

        confirm_btn = QtWidgets.QPushButton("Confirm", btns_widget)
        confirm_btn.setObjectName("ConfirmButton")
        confirm_btn.clicked.connect(self.close_requested)

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addWidget(back_btn, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(select_all_btn, 0)
        btns_layout.addWidget(clear_btn, 0)
        btns_layout.addWidget(swap_btn, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(confirm_btn, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(filter_input, 0)
        main_layout.addWidget(scroll_area)
        main_layout.addWidget(btns_sep, 0)
        main_layout.addWidget(btns_widget, 0)

        filter_timeout.timeout.connect(self._on_filter_timeout)
        filter_input.textChanged.connect(self._on_filter_change)
        filter_input.returnPressed.connect(self.close_requested)
        back_btn.clicked.connect(self.back_requested)
        select_all_btn.clicked.connect(self._on_select_all)
        clear_btn.clicked.connect(self._on_clear_selection)
        swap_btn.clicked.connect(self._on_swap_selection)

        self._filter_timeout = filter_timeout
        self._filter_input = filter_input
        self._btns_widget = btns_widget
        self._multiselection = False
        self._content_layout = content_layout
        self._last_selected_widget = None
        self._widgets_by_id = {}

    def showEvent(self, event):
        super().showEvent(event)
        self._filter_timeout.start()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            event.accept()
            self.close_requested.emit()
            return

        if event.key() in (
            QtCore.Qt.Key_Backtab,
            QtCore.Qt.Key_Backspace,
        ):
            event.accept()
            set_line_edit_focus(self._filter_input, backspace=True)
            return

        valid_modifiers = event.modifiers() in (
            QtCore.Qt.NoModifier,
            QtCore.Qt.ShiftModifier,
        )
        if valid_modifiers and event.key() not in (
            QtCore.Qt.Key_Escape,
            QtCore.Qt.Key_Tab,
            QtCore.Qt.Key_Return,
        ):
            text = event.text()
            if text:
                event.accept()
                set_line_edit_focus(self._filter_input, append_text=text)
                return

        super().keyPressEvent(event)

    def set_value(self, value):
        current_value = self.get_value()
        if self._multiselection:
            if value is None:
                value = []
            if not isinstance(value, list):
                value = [value]
            for widget in self._widgets_by_id.values():
                selected = widget.get_value() in value
                if selected and self._last_selected_widget is None:
                    self._last_selected_widget = widget
                widget.set_selected(selected)

            if value != current_value:
                self.value_changed.emit()
            return

        if isinstance(value, list):
            if len(value) > 0:
                value = value[0]
            else:
                value = None

        if value is None:
            widget = next(iter(self._widgets_by_id.values()))
            value = widget.get_value()

        self._last_selected_widget = None
        for widget in self._widgets_by_id.values():
            selected = widget.get_value() in value
            widget.set_selected(selected)
            if selected:
                self._last_selected_widget = widget

        if self._last_selected_widget is None:
            widget = next(iter(self._widgets_by_id.values()))
            self._last_selected_widget = widget
            widget.set_selected(True)

        if value != current_value:
            self.value_changed.emit()

    def set_multiselection(self, multiselection: bool):
        self._multiselection = multiselection
        if not self._widgets_by_id or not self._multiselection:
            self._btns_widget.setVisible(False)
        else:
            self._btns_widget.setVisible(True)

        if not self._widgets_by_id or self._multiselection:
            return

        value_changed = False
        if self._last_selected_widget is None:
            value_changed = True
            self._last_selected_widget = next(
                iter(self._widgets_by_id.values())
            )
        for widget in self._widgets_by_id.values():
            widget.set_selected(widget is self._last_selected_widget)

        if value_changed:
            self.value_changed.emit()

    def get_value(self):
        """Get the value from the items view."""
        if self._multiselection:
            return [
                widget.get_value()
                for widget in self._widgets_by_id.values()
                if widget.is_selected()
            ]
        if self._last_selected_widget is not None:
            return self._last_selected_widget.get_value()
        return None

    def set_items(self, items: list[dict[str, Any]]):
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)
                widget.deleteLater()

        self._widgets_by_id = {}
        self._last_selected_widget = None
        # Change filter
        self._filter_input.setText("")

        for item in items:
            widget_id = uuid.uuid4().hex
            widget = FilterValueItemButton(
                widget_id,
                item["value"],
                item.get("icon"),
                item.get("color"),
                self,
            )
            widget.selected.connect(self._on_item_clicked)
            self._widgets_by_id[widget_id] = widget
            self._content_layout.addWidget(widget, 0)

        if self._content_layout.count() == 0:
            empty_label = QtWidgets.QLabel(
                "No items to select from...", self
            )
            self._btns_widget.setVisible(False)
            self._filter_input.setVisible(False)
            self._content_layout.addWidget(empty_label, 0)
        else:
            self._filter_input.setVisible(True)
            self._btns_widget.setVisible(self._multiselection)
        self._content_layout.addStretch(1)

    def _on_filter_timeout(self):
        self._filter_input.setFocus()

    def _on_filter_change(self, text):
        text = text.lower()
        for widget in self._widgets_by_id.values():
            visible = not text or text in widget.get_value().lower()
            widget.setVisible(visible)

    def _on_select_all(self):
        changed = False
        for widget in self._widgets_by_id.values():
            if not widget.is_selected():
                changed = True
                widget.set_selected(True)
                if self._last_selected_widget is None:
                    self._last_selected_widget = widget

        if changed:
            self.value_changed.emit()

    def _on_swap_selection(self):
        self._last_selected_widget = None
        for widget in self._widgets_by_id.values():
            selected = not widget.is_selected()
            widget.set_selected(selected)
            if selected and self._last_selected_widget is None:
                self._last_selected_widget = widget

        self.value_changed.emit()

    def _on_clear_selection(self):
        self._last_selected_widget = None
        changed = False
        for widget in self._widgets_by_id.values():
            if widget.is_selected():
                changed = True
                widget.set_selected(False)

        if changed:
            self.value_changed.emit()

    def _on_item_clicked(self, widget_id):
        widget = self._widgets_by_id.get(widget_id)
        if widget is None:
            return

        previous_widget = self._last_selected_widget
        self._last_selected_widget = widget
        if self._multiselection:
            widget.set_selected(not widget.is_selected())
        else:
            widget.set_selected(True)
            if previous_widget is not None:
                previous_widget.set_selected(False)
        self.value_changed.emit()


class FilterValuePopup(QtWidgets.QWidget):
    value_changed = QtCore.Signal(str)
    closed = QtCore.Signal(str)
    back_requested = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        shadow_frame = QtWidgets.QFrame(self)
        shadow_frame.setObjectName("ShadowFrame")

        wrapper = QtWidgets.QWidget(self)
        wrapper.setObjectName("PopupWrapper")

        text_input = FilterValueTextInput(wrapper)
        text_input.setVisible(False)

        items_view = FilterValueItemsView(wrapper)
        items_view.setVisible(False)

        wraper_layout = QtWidgets.QVBoxLayout(wrapper)
        wraper_layout.setContentsMargins(5, 5, 5, 5)
        wraper_layout.setSpacing(5)
        wraper_layout.addWidget(text_input, 0)
        wraper_layout.addWidget(items_view, 0)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.addWidget(wrapper)

        text_input.value_changed.connect(self._text_changed)
        text_input.close_requested.connect(self._close_requested)
        text_input.back_requested.connect(self._back_requested)

        items_view.value_changed.connect(self._selection_changed)
        items_view.close_requested.connect(self._close_requested)
        items_view.back_requested.connect(self._back_requested)

        shadow_frame.stackUnder(wrapper)

        self._shadow_frame = shadow_frame
        self._wrapper = wrapper
        self._wrapper_layout = wraper_layout
        self._text_input = text_input
        self._items_view = items_view

        self._active_widget = None
        self._filter_name = None
        self._preferred_width = None

    def set_preferred_width(self, width: int):
        self._preferred_width = width

    def sizeHint(self):
        sh = super().sizeHint()
        if self._preferred_width is not None:
            sh.setWidth(self._preferred_width)
        return sh

    def set_text_filter(self, text: str):
        if self._active_widget is None:
            return

        if self._active_widget is self._text_input:
            self._active_widget.set_text_filter(text)

    def set_filter_item(
        self,
        filter_def: FilterDefinition,
        value,
    ):
        self._text_input.setVisible(False)
        self._items_view.setVisible(False)
        self._filter_name = filter_def.name
        self._active_widget = None
        if filter_def.filter_type == "text":
            if filter_def.items:
                if value is None:
                    value = filter_def.items[0]["value"]
                self._active_widget = self._items_view
                self._items_view.set_items(filter_def.items)
                self._items_view.set_multiselection(False)
                self._items_view.set_value(value)
            else:
                if value is None:
                    value = ""
                self._text_input.set_placeholder_text(
                    filter_def.placeholder or ""
                )
                self._text_input.set_value(value)
                self._active_widget = self._text_input

        elif filter_def.filter_type == "list":
            if value is None:
                value = []
            self._items_view.set_items(filter_def.items)
            self._items_view.set_multiselection(True)
            self._items_view.set_value(value)
            self._active_widget = self._items_view

        if self._active_widget is not None:
            self._active_widget.setVisible(True)

    def showEvent(self, event):
        super().showEvent(event)
        if self._active_widget is not None:
            self._active_widget.setFocus()
        self._update_shadow()

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit(self._filter_name)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit(self._filter_name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_shadow()

    def _update_shadow(self):
        geo = self.geometry()
        geo.moveTopLeft(QtCore.QPoint(0, 0))
        self._shadow_frame.setGeometry(geo)

    def get_value(self):
        """Get the value from the active widget."""
        if self._active_widget is self._text_input:
            return self._text_input.get_value()
        elif self._active_widget is self._items_view:
            return self._active_widget.get_value()
        return None

    def _text_changed(self):
        """Handle text change in the text input."""
        if self._active_widget is self._text_input:
            # Emit value changed signal if text input is active
            self.value_changed.emit(self._filter_name)

    def _selection_changed(self):
        self.value_changed.emit(self._filter_name)

    def _close_requested(self):
        self.close()

    def _back_requested(self):
        self.back_requested.emit(self._filter_name)
        self.close()


class FiltersBar(BaseClickableFrame):
    filter_changed = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        search_icon = get_qt_icon({
            "type": "material-symbols",
            "name": "search",
            "color": "#FFFFFF",
        })
        search_btn = SquareButton(self)
        search_btn.setIcon(search_icon)
        search_btn.setFlat(True)
        search_btn.setObjectName("SearchButton")

        # Wrapper is used to avoid squashing filters
        # - the filters are positioned manually without layout
        filters_wrap = QtWidgets.QWidget(self)
        filters_wrap.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Widget where set filters are displayed
        filters_widget = QtWidgets.QWidget(filters_wrap)
        filters_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        filters_layout = QtWidgets.QHBoxLayout(filters_widget)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.addStretch(1)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(5)
        main_layout.addWidget(search_btn, 0)
        main_layout.addWidget(filters_wrap, 1)

        filters_popup = FiltersPopup(self)
        filter_value_popup = FilterValuePopup(self)

        search_btn.clicked.connect(self._on_filters_request)
        filters_popup.text_filter_requested.connect(
            self._on_text_filter_request
        )

        self._search_btn = search_btn
        self._filters_wrap = filters_wrap
        self._filters_widget = filters_widget
        self._filters_layout = filters_layout
        self._widgets_by_name = {}
        self._filter_defs_by_name = {}
        self._filters_popup = filters_popup
        self._filter_value_popup = filter_value_popup

    def showEvent(self, event):
        super().showEvent(event)
        self._update_filters_geo()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_filters_geo()

    def show_filters_popup(self):
        filter_defs = [
            filter_def
            for filter_def in self._filter_defs_by_name.values()
            if filter_def.name not in self._widgets_by_name
        ]
        filters_popup = FiltersPopup(self)
        filters_popup.filter_requested.connect(self._on_filter_request)
        filters_popup.text_filter_requested.connect(
            self._on_text_filter_request
        )
        filters_popup.set_filter_items(filter_defs)
        filters_popup.set_preferred_width(self.width())

        old_popup, self._filters_popup = self._filters_popup, filters_popup

        self._filter_value_popup.setVisible(False)
        old_popup.setVisible(False)
        old_popup.deleteLater()

        self._show_popup(filters_popup)

    def set_search_items(self, filter_defs: list[FilterDefinition]):
        self._filter_defs_by_name = {
            filter_def.name: filter_def
            for filter_def in filter_defs
        }

    def get_filter_value(self, name: str) -> Optional[Any]:
        """Get the value of a filter by its name."""
        item_widget = self._widgets_by_name.get(name)
        if item_widget is not None:
            value = item_widget.get_value()
            if isinstance(value, list) and len(value) == 0:
                return None
            return value
        return None

    def set_filter_value(self, name: str, value: Any):
        """Set the value of a filter by its name."""
        if name not in self._filter_defs_by_name:
            return

        item_widget = self._widgets_by_name.get(name)
        if item_widget is None:
            self.add_item(name)
            item_widget = self._widgets_by_name.get(name)

        item_widget.set_value(value)
        self.filter_changed.emit(name)

    def add_item(self, name: str):
        """Add a new item to the search bar.

        Args:
            name (str): Search definition name.

        """
        filter_def = self._filter_defs_by_name.get(name)
        if filter_def is None:
            return

        item_widget = self._widgets_by_name.get(name)
        if item_widget is not None:
            return

        item_widget = SearchItemDisplayWidget(
            filter_def,
            parent=self._filters_widget,
        )
        item_widget.edit_requested.connect(self._on_filter_request)
        item_widget.close_requested.connect(self._on_item_close_requested)
        self._widgets_by_name[name] = item_widget
        idx = self._filters_layout.count() - 1
        self._filters_layout.insertWidget(idx, item_widget, 0)

    def _update_filters_geo(self):
        geo = self._filters_wrap.geometry()
        geo.moveTopLeft(QtCore.QPoint(0, 0))
        # Arbitrary width
        geo.setWidth(3000)

        self._filters_widget.setGeometry(geo)

    def _mouse_release_callback(self):
        self.show_filters_popup()

    def _on_filters_request(self):
        self.show_filters_popup()

    def _on_text_filter_request(self, text: str):
        if "product_name" not in self._filter_defs_by_name:
            return

        self._on_filter_request("product_name")
        self._filter_value_popup.set_text_filter(text)

    def _on_filter_request(self, filter_name: str):
        """Handle filter request from the popup."""
        self.add_item(filter_name)
        self._filters_popup.hide()
        filter_def = self._filter_defs_by_name.get(filter_name)
        widget = self._widgets_by_name.get(filter_name)
        value = None
        if widget is not None:
            value = widget.get_value()

        filter_value_popup = FilterValuePopup(self)
        filter_value_popup.set_preferred_width(self.width())
        filter_value_popup.set_filter_item(filter_def, value)
        filter_value_popup.value_changed.connect(self._on_filter_value_change)
        filter_value_popup.closed.connect(self._on_filter_value_closed)
        filter_value_popup.back_requested.connect(self._on_filter_value_back)

        old_popup, self._filter_value_popup = (
            self._filter_value_popup, filter_value_popup
        )

        old_popup.setVisible(False)
        old_popup.deleteLater()

        self._filters_popup.setVisible(False)

        self._show_popup(filter_value_popup)
        self._on_filter_value_change(filter_def.name)

    def _show_popup(self, popup: QtWidgets.QWidget):
        """Show a popup widget."""
        geo = self.geometry()
        bl_pos_g = self.mapToGlobal(QtCore.QPoint(0, geo.height() + 5))
        popup.show()
        popup.move(bl_pos_g.x(), bl_pos_g.y())
        popup.raise_()

    def _on_filter_value_change(self, name):
        value = self._filter_value_popup.get_value()
        item_widget = self._widgets_by_name.get(name)
        item_widget.set_value(value)
        self.filter_changed.emit(name)

    def _on_filter_value_closed(self, name):
        widget = self._widgets_by_name.get(name)
        if widget is None:
            return

        value = widget.get_value()
        if not value:
            self._on_item_close_requested(name)

    def _on_filter_value_back(self, name):
        self._on_filter_value_closed(name)
        self.show_filters_popup()

    def _on_item_close_requested(self, name):
        widget = self._widgets_by_name.pop(name, None)
        if widget is not None:
            idx = self._filters_layout.indexOf(widget)
            if idx > -1:
                self._filters_layout.takeAt(idx)
                widget.setVisible(False)
                widget.deleteLater()
                self.filter_changed.emit(name)
