from __future__ import annotations
import typing
from typing import List, Tuple, Optional, Iterable, Any

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.lib import (
    checkstate_int_to_enum,
    checkstate_enum_to_int,
)
from ayon_core.tools.utils.constants import (
    CHECKED_INT,
    UNCHECKED_INT,
    ITEM_IS_USER_TRISTATE,
)
if typing.TYPE_CHECKING:
    from ayon_core.tools.loader.abstract import FrontendLoaderController

VALUE_ITEM_TYPE = 0
STANDARD_ITEM_TYPE = 1
SEPARATOR_ITEM_TYPE = 2

VALUE_ITEM_SUBTYPE = 0
SELECT_ALL_SUBTYPE = 1
DESELECT_ALL_SUBTYPE = 2
SWAP_STATE_SUBTYPE = 3


class BaseQtModel(QtGui.QStandardItemModel):
    _empty_icon = None

    def __init__(
        self,
        item_type_role: int,
        item_subtype_role: int,
        empty_values_label: str,
        controller: FrontendLoaderController,
    ):
        self._item_type_role = item_type_role
        self._item_subtype_role = item_subtype_role
        self._empty_values_label = empty_values_label
        self._controller = controller

        self._last_project = None

        self._select_project_item = None
        self._empty_values_item = None

        self._select_all_item = None
        self._deselect_all_item = None
        self._swap_states_item = None

        super().__init__()

        self.refresh(None)

    def _get_standard_items(self) -> list[QtGui.QStandardItem]:
        raise NotImplementedError(
            "'_get_standard_items' is not implemented"
            f" for {self.__class__}"
        )

    def _clear_standard_items(self):
        raise NotImplementedError(
            "'_clear_standard_items' is not implemented"
            f" for {self.__class__}"
        )

    def _prepare_new_value_items(
        self, project_name: str, project_changed: bool
    ) -> tuple[
        list[QtGui.QStandardItem], list[QtGui.QStandardItem]
    ]:
        raise NotImplementedError(
            "'_prepare_new_value_items' is not implemented"
            f" for {self.__class__}"
        )

    def refresh(self, project_name: Optional[str]):
        # New project was selected
        project_changed = False
        if project_name != self._last_project:
            self._last_project = project_name
            project_changed = True

        if project_name is None:
            self._add_select_project_item()
            return

        value_items, items_to_remove = self._prepare_new_value_items(
            project_name, project_changed
        )
        if not value_items:
            self._add_empty_values_item()
            return

        self._remove_empty_items()

        root_item = self.invisibleRootItem()
        for row_idx, value_item in enumerate(value_items):
            if value_item.row() == row_idx:
                continue
            if value_item.row() >= 0:
                root_item.takeRow(value_item.row())
            root_item.insertRow(row_idx, value_item)

        for item in items_to_remove:
            root_item.removeRow(item.row())

        self._add_selection_items()

    def setData(self, index, value, role):
        if role == QtCore.Qt.CheckStateRole and index.isValid():
            item_subtype = index.data(self._item_subtype_role)
            if item_subtype == SELECT_ALL_SUBTYPE:
                for item in self._get_standard_items():
                    item.setCheckState(QtCore.Qt.Checked)
                return True
            if item_subtype == DESELECT_ALL_SUBTYPE:
                for item in self._get_standard_items():
                    item.setCheckState(QtCore.Qt.Unchecked)
                return True
            if item_subtype == SWAP_STATE_SUBTYPE:
                for item in self._get_standard_items():
                    current_state = item.checkState()
                    item.setCheckState(
                        QtCore.Qt.Checked
                        if current_state == QtCore.Qt.Unchecked
                        else QtCore.Qt.Unchecked
                    )
                return True
        return super().setData(index, value, role)

    @classmethod
    def _get_empty_icon(cls):
        if cls._empty_icon is None:
            pix = QtGui.QPixmap(1, 1)
            pix.fill(QtCore.Qt.transparent)
            cls._empty_icon = QtGui.QIcon(pix)
        return cls._empty_icon

    def _init_default_items(self):
        if self._empty_values_item is not None:
            return

        empty_values_item = QtGui.QStandardItem(self._empty_values_label)
        select_project_item = QtGui.QStandardItem("Select project...")

        select_all_item = QtGui.QStandardItem("Select all")
        deselect_all_item = QtGui.QStandardItem("Deselect all")
        swap_states_item = QtGui.QStandardItem("Swap")

        for item in (
            empty_values_item,
            select_project_item,
            select_all_item,
            deselect_all_item,
            swap_states_item,
        ):
            item.setData(STANDARD_ITEM_TYPE, self._item_type_role)

        select_all_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "done_all",
            "color": "white"
        }))
        deselect_all_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "remove_done",
            "color": "white"
        }))
        swap_states_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "swap_horiz",
            "color": "white"
        }))

        for item in (
            empty_values_item,
            select_project_item,
        ):
            item.setFlags(QtCore.Qt.NoItemFlags)

        for item, item_type in (
            (select_all_item, SELECT_ALL_SUBTYPE),
            (deselect_all_item, DESELECT_ALL_SUBTYPE),
            (swap_states_item, SWAP_STATE_SUBTYPE),
        ):
            item.setData(item_type, self._item_subtype_role)

        for item in (
            select_all_item,
            deselect_all_item,
            swap_states_item,
        ):
            item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsUserCheckable
            )

        self._empty_values_item = empty_values_item
        self._select_project_item = select_project_item

        self._select_all_item = select_all_item
        self._deselect_all_item = deselect_all_item
        self._swap_states_item = swap_states_item

    def _get_empty_values_item(self):
        self._init_default_items()
        return self._empty_values_item

    def _get_select_project_item(self):
        self._init_default_items()
        return self._select_project_item

    def _get_empty_items(self):
        self._init_default_items()
        return [
            self._empty_values_item,
            self._select_project_item,
        ]

    def _get_selection_items(self):
        self._init_default_items()
        return [
            self._select_all_item,
            self._deselect_all_item,
            self._swap_states_item,
        ]

    def _get_default_items(self):
        return self._get_empty_items() + self._get_selection_items()

    def _add_select_project_item(self):
        item = self._get_select_project_item()
        if item.row() < 0:
            self._remove_items()
            root_item = self.invisibleRootItem()
            root_item.appendRow(item)

    def _add_empty_values_item(self):
        item = self._get_empty_values_item()
        if item.row() < 0:
            self._remove_items()
            root_item = self.invisibleRootItem()
            root_item.appendRow(item)

    def _add_selection_items(self):
        root_item = self.invisibleRootItem()
        items = self._get_selection_items()
        for item in self._get_selection_items():
            row = item.row()
            if row >= 0:
                root_item.takeRow(row)
        root_item.appendRows(items)

    def _remove_items(self):
        root_item = self.invisibleRootItem()
        for item in self._get_default_items():
            if item.row() < 0:
                continue
            root_item.takeRow(item.row())

        root_item.removeRows(0, root_item.rowCount())
        self._clear_standard_items()

    def _remove_empty_items(self):
        root_item = self.invisibleRootItem()
        for item in self._get_empty_items():
            if item.row() < 0:
                continue
            root_item.takeRow(item.row())


class CustomPaintDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate showing status name and short name."""
    _empty_icon = None
    _checked_value = checkstate_enum_to_int(QtCore.Qt.Checked)
    _checked_bg_color = QtGui.QColor("#2C3B4C")

    def __init__(
        self,
        text_role: int,
        short_text_role: int,
        text_color_role: int,
        icon_role: int,
        item_type_role: Optional[int] = None,
        parent=None
    ):
        super().__init__(parent)
        self._text_role = text_role
        self._text_color_role = text_color_role
        self._short_text_role = short_text_role
        self._icon_role = icon_role
        self._item_type_role = item_type_role

    @classmethod
    def _get_empty_icon(cls):
        if cls._empty_icon is None:
            pix = QtGui.QPixmap(1, 1)
            pix.fill(QtCore.Qt.transparent)
            cls._empty_icon = QtGui.QIcon(pix)
        return cls._empty_icon

    def paint(self, painter, option, index):
        item_type = None
        if self._item_type_role is not None:
            item_type = index.data(self._item_type_role)

        if item_type is None:
            item_type = VALUE_ITEM_TYPE

        if item_type == STANDARD_ITEM_TYPE:
            super().paint(painter, option, index)
            return

        elif item_type == SEPARATOR_ITEM_TYPE:
            self._paint_separator(painter, option, index)
            return

        if option.widget:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()

        self.initStyleOption(option, index)

        mode = QtGui.QIcon.Normal
        if not (option.state & QtWidgets.QStyle.State_Enabled):
            mode = QtGui.QIcon.Disabled
        elif option.state & QtWidgets.QStyle.State_Selected:
            mode = QtGui.QIcon.Selected
        state = QtGui.QIcon.Off
        if option.state & QtWidgets.QStyle.State_Open:
            state = QtGui.QIcon.On
        icon = self._get_index_icon(index)
        if icon is None or icon.isNull():
            icon = self._get_empty_icon()

        option.features |= QtWidgets.QStyleOptionViewItem.HasDecoration

        # Disable visible check indicator
        # - checkstate is displayed by background color
        option.features &= (
            ~QtWidgets.QStyleOptionViewItem.HasCheckIndicator
        )

        option.icon = icon
        act_size = icon.actualSize(option.decorationSize, mode, state)
        option.decorationSize = QtCore.QSize(
            min(option.decorationSize.width(), act_size.width()),
            min(option.decorationSize.height(), act_size.height())
        )

        text = self._get_index_name(index)
        if text:
            option.features |= QtWidgets.QStyleOptionViewItem.HasDisplay
            option.text = text

        painter.save()
        painter.setClipRect(option.rect)

        is_checked = (
            index.data(QtCore.Qt.CheckStateRole) == self._checked_value
        )
        if is_checked:
            painter.fillRect(option.rect, self._checked_bg_color)

        icon_rect = style.subElementRect(
            QtWidgets.QCommonStyle.SE_ItemViewItemDecoration,
            option,
            option.widget
        )
        text_rect = style.subElementRect(
            QtWidgets.QCommonStyle.SE_ItemViewItemText,
            option,
            option.widget
        )

        # Draw background
        style.drawPrimitive(
            QtWidgets.QCommonStyle.PE_PanelItemViewItem,
            option,
            painter,
            option.widget
        )

        # Draw icon
        option.icon.paint(
            painter,
            icon_rect,
            option.decorationAlignment,
            mode,
            state
        )
        fm = QtGui.QFontMetrics(option.font)
        if text_rect.width() < fm.width(text):
            text = self._get_index_short_name(index)
            if not text or text_rect.width() < fm.width(text):
                text = ""

        fg_color = self._get_index_text_color(index)
        pen = painter.pen()
        pen.setColor(fg_color)
        painter.setPen(pen)

        painter.drawText(
            text_rect,
            option.displayAlignment,
            text
        )

        if option.state & QtWidgets.QStyle.State_HasFocus:
            focus_opt = QtWidgets.QStyleOptionFocusRect()
            focus_opt.state = option.state
            focus_opt.direction = option.direction
            focus_opt.rect = option.rect
            focus_opt.fontMetrics = option.fontMetrics
            focus_opt.palette = option.palette

            focus_opt.rect = style.subElementRect(
                QtWidgets.QCommonStyle.SE_ItemViewItemFocusRect,
                option,
                option.widget
            )
            focus_opt.state |= (
                QtWidgets.QStyle.State_KeyboardFocusChange
                | QtWidgets.QStyle.State_Item
            )
            focus_opt.backgroundColor = option.palette.color(
                (
                    QtGui.QPalette.Normal
                    if option.state & QtWidgets.QStyle.State_Enabled
                    else QtGui.QPalette.Disabled
                ),
                (
                    QtGui.QPalette.Highlight
                    if option.state & QtWidgets.QStyle.State_Selected
                    else QtGui.QPalette.Window
                )
            )
            style.drawPrimitive(
                QtWidgets.QCommonStyle.PE_FrameFocusRect,
                focus_opt,
                painter,
                option.widget
            )

        painter.restore()

    def _paint_separator(self, painter, option, index):
        painter.save()
        painter.setClipRect(option.rect)

        style = option.widget.style()
        style.drawPrimitive(
            QtWidgets.QCommonStyle.PE_PanelItemViewItem,
            option,
            painter,
            option.widget
        )

        pen = painter.pen()
        pen.setWidth(2)
        painter.setPen(pen)
        mid_y = (option.rect.top() + option.rect.bottom()) * 0.5
        painter.drawLine(
            QtCore.QPointF(option.rect.left(), mid_y),
            QtCore.QPointF(option.rect.right(), mid_y)
        )

        painter.restore()

    def _get_index_name(self, index):
        return index.data(self._text_role)

    def _get_index_short_name(self, index):
        if self._short_text_role is None:
            return None
        return index.data(self._short_text_role)

    def _get_index_text_color(self, index):
        color = None
        if self._text_color_role is not None:
            color = index.data(self._text_color_role)
        if color is not None:
            return QtGui.QColor(color)
        return QtGui.QColor(QtCore.Qt.white)

    def _get_index_icon(self, index):
        icon = None
        if self._icon_role is not None:
            icon = index.data(self._icon_role)
        if icon is None:
            return QtGui.QIcon()
        return icon


class CustomPaintMultiselectComboBox(QtWidgets.QComboBox):
    value_changed = QtCore.Signal()
    focused_in = QtCore.Signal()

    ignored_keys = {
        QtCore.Qt.Key_Up,
        QtCore.Qt.Key_Down,
        QtCore.Qt.Key_PageDown,
        QtCore.Qt.Key_PageUp,
        QtCore.Qt.Key_Home,
        QtCore.Qt.Key_End,
    }
    _top_bottom_margins = 1
    _top_bottom_padding = 2
    _left_right_padding = 3
    _item_bg_color = QtGui.QColor("#31424e")

    def __init__(
        self,
        text_role,
        short_text_role,
        text_color_role,
        icon_role,
        value_role=None,
        item_type_role=None,
        model=None,
        placeholder=None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        if model is not None:
            self.setModel(model)

        combo_view = QtWidgets.QListView(self)

        self.setView(combo_view)

        item_delegate = CustomPaintDelegate(
            text_role=text_role,
            short_text_role=short_text_role,
            text_color_role=text_color_role,
            icon_role=icon_role,
            item_type_role=item_type_role,
            parent=combo_view,
        )
        combo_view.setItemDelegateForColumn(0, item_delegate)

        if value_role is None:
            value_role = text_role

        self._combo_view = combo_view
        self._item_delegate = item_delegate
        self._value_role = value_role
        self._text_role = text_role
        self._short_text_role = short_text_role
        self._text_color_role = text_color_role
        self._icon_role = icon_role
        self._item_type_role = item_type_role

        self._popup_is_shown = False
        self._block_mouse_release_timer = QtCore.QTimer(self, singleShot=True)
        self._initial_mouse_pos = None
        self._placeholder_text = placeholder

        self._custom_text = None
        self._all_unchecked_as_checked = True

    def all_unchecked_as_checked(self) -> bool:
        return self._all_unchecked_as_checked

    def set_all_unchecked_as_checked(self, value: bool):
        """Set if all unchecked items should be treated as checked.

        Args:
            value (bool): If True, all unchecked items will be treated
                as checked.

        """
        self._all_unchecked_as_checked = value

    def get_placeholder_text(self) -> Optional[str]:
        return self._placeholder_text

    def set_placeholder_text(self, text: Optional[str]):
        """Set the placeholder text.

        Text shown when nothing is selected.

        Args:
            text (str | None): The placeholder text.

        """
        if text == self._placeholder_text:
            return
        self._placeholder_text = text
        self.repaint()

    def set_custom_text(self, text: Optional[str]):
        """Set the placeholder text.

        Text always shown in combobox field.

        Args:
            text (str | None): The text. Use 'None' to reset to default.

        """
        if text == self._custom_text:
            return
        self._custom_text = text
        self.repaint()

    def focusInEvent(self, event):
        self.focused_in.emit()
        return super().focusInEvent(event)

    def mousePressEvent(self, event):
        """Reimplemented."""
        self._popup_is_shown = False
        super().mousePressEvent(event)
        if self._popup_is_shown:
            self._initial_mouse_pos = self.mapToGlobal(event.pos())
            self._block_mouse_release_timer.start(
                QtWidgets.QApplication.doubleClickInterval()
            )

    def showPopup(self):
        """Reimplemented."""
        super().showPopup()
        view = self.view()
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        self._popup_is_shown = True

    def hidePopup(self):
        """Reimplemented."""
        self.view().removeEventFilter(self)
        self.view().viewport().removeEventFilter(self)
        self._popup_is_shown = False
        self._initial_mouse_pos = None
        super().hidePopup()
        self.view().clearFocus()

    def _event_popup_shown(self, obj, event):
        if not self._popup_is_shown:
            return

        current_index = self.view().currentIndex()
        model = self.model()

        if event.type() == QtCore.QEvent.MouseMove:
            if (
                self.view().isVisible()
                and self._initial_mouse_pos is not None
                and self._block_mouse_release_timer.isActive()
            ):
                diff = obj.mapToGlobal(event.pos()) - self._initial_mouse_pos
                if diff.manhattanLength() > 9:
                    self._block_mouse_release_timer.stop()
            return

        index_flags = current_index.flags()
        state = checkstate_int_to_enum(
            current_index.data(QtCore.Qt.CheckStateRole)
        )

        new_state = None

        if event.type() == QtCore.QEvent.MouseButtonRelease:
            new_state = self._mouse_released_event_handle(
                event, current_index, index_flags, state
            )

        elif event.type() == QtCore.QEvent.KeyPress:
            new_state = self._key_press_event_handler(
                event, current_index, index_flags, state
            )

        if new_state is not None:
            model.setData(current_index, new_state, QtCore.Qt.CheckStateRole)
            self.view().update(current_index)
            self.repaint()
            self.value_changed.emit()
            return True

    def eventFilter(self, obj, event):
        """Reimplemented."""
        result = self._event_popup_shown(obj, event)
        if result is not None:
            return result

        return super().eventFilter(obj, event)

    def addItem(self, *args, **kwargs):
        idx = self.count()
        super().addItem(*args, **kwargs)
        self.model().item(idx).setCheckable(True)

    def paintEvent(self, event):
        """Reimplemented."""
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, option)

        idxs = self._get_checked_idx()
        # draw the icon and text
        draw_items = False
        combotext = None
        if self._custom_text is not None:
            combotext = self._custom_text
        elif not idxs:
            combotext = self._placeholder_text
        else:
            draw_items = True

        content_field_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            option,
            QtWidgets.QStyle.SC_ComboBoxEditField
        ).adjusted(1, 0, -1, 0)

        if draw_items:
            self._paint_items(painter, idxs, content_field_rect)
        else:
            color = option.palette.color(QtGui.QPalette.Text)
            color.setAlpha(67)
            pen = painter.pen()
            pen.setColor(color)
            painter.setPen(pen)
            painter.drawText(
                content_field_rect,
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                combotext
            )

        painter.end()

    def _paint_items(self, painter, indexes, content_rect):
        origin_rect = QtCore.QRect(content_rect)

        model = self.model()
        available_width = content_rect.width()
        total_used_width = 0

        painter.save()

        spacing = 2

        for idx in indexes:
            index = model.index(idx, 0)
            if not index.isValid():
                continue

            icon = index.data(self._icon_role)
            text = index.data(self._text_role)
            valid_icon = icon is not None and not icon.isNull()
            if valid_icon:
                sizes = icon.availableSizes()
                if sizes:
                    valid_icon = any(size.width() > 1 for size in sizes)

            if valid_icon:
                metrics = self.fontMetrics()
                icon_rect = QtCore.QRect(content_rect)
                diff = icon_rect.height() - metrics.height()
                if diff < 0:
                    diff = 0
                top_offset = diff // 2
                bottom_offset = diff - top_offset
                icon_rect.adjust(0, top_offset, 0, -bottom_offset)
                used_width = metrics.height()
                if total_used_width > 0:
                    total_used_width += spacing
                total_used_width += used_width
                if total_used_width > available_width:
                    break

                icon_rect.setWidth(used_width)
                icon.paint(
                    painter,
                    icon_rect,
                    QtCore.Qt.AlignCenter,
                    QtGui.QIcon.Normal,
                    QtGui.QIcon.On
                )
                content_rect.setLeft(icon_rect.right() + spacing)

            elif text:
                bg_height = (
                    content_rect.height()
                    - (2 * self._top_bottom_margins)
                )
                font_height = bg_height - (2 * self._top_bottom_padding)

                bg_top_y = content_rect.y() + self._top_bottom_margins

                font = self.font()
                font.setPixelSize(font_height)
                metrics = QtGui.QFontMetrics(font)
                painter.setFont(font)

                label_rect = metrics.boundingRect(text)

                bg_width = label_rect.width() + (2 * self._left_right_padding)
                if total_used_width > 0:
                    total_used_width += spacing
                total_used_width += bg_width
                if total_used_width > available_width:
                    break

                bg_rect = QtCore.QRectF(label_rect)
                bg_rect.moveTop(bg_top_y)
                bg_rect.moveLeft(content_rect.left())
                bg_rect.setWidth(bg_width)
                bg_rect.setHeight(bg_height)

                label_rect.moveTop(bg_top_y)
                label_rect.moveLeft(
                    content_rect.left() + self._left_right_padding
                )

                path = QtGui.QPainterPath()
                path.addRoundedRect(bg_rect, 5, 5)

                painter.fillPath(path, self._item_bg_color)
                painter.drawText(label_rect, QtCore.Qt.AlignCenter, text)

                content_rect.setLeft(bg_rect.right() + spacing)

        painter.restore()

        if total_used_width > available_width:
            ellide_dots = chr(0x2026)
            painter.drawText(origin_rect, QtCore.Qt.AlignRight, ellide_dots)

    def setItemCheckState(self, index, state):
        self.setItemData(index, state, QtCore.Qt.CheckStateRole)

    def set_value(
        self,
        values: Optional[Iterable[Any]],
        role: Optional[int] = None,
    ):
        if role is None:
            role = self._value_role

        for idx in range(self.count()):
            value = self.itemData(idx, role=role)
            check_state = CHECKED_INT
            if values is None or value not in values:
                check_state = UNCHECKED_INT
            self.setItemData(idx, check_state, QtCore.Qt.CheckStateRole)
        self.repaint()

    def get_value_info(
        self,
        role: Optional[int] = None,
        propagate_all_unchecked_as_checked: bool = None
    ) -> List[Tuple[Any, bool]]:
        """Get the values and their checked state.

        Args:
            role (int | None): The role to get the values from.
                If None, the default value role is used.
            propagate_all_unchecked_as_checked (bool | None): If True,
                all unchecked items will be treated as checked.
                If None, the current value of
                'propagate_all_unchecked_as_checked' is used.

        Returns:
            List[Tuple[Any, bool]]: The values and their checked state.

        """
        if role is None:
            role = self._value_role

        if propagate_all_unchecked_as_checked is None:
            propagate_all_unchecked_as_checked = (
                self._all_unchecked_as_checked
            )

        items = []
        all_unchecked = True
        for idx in range(self.count()):
            item_type = self.itemData(idx, role=self._item_type_role)
            if item_type is not None and item_type != VALUE_ITEM_TYPE:
                continue

            state = checkstate_int_to_enum(
                self.itemData(idx, role=QtCore.Qt.CheckStateRole)
            )
            checked = state == QtCore.Qt.Checked
            if checked:
                all_unchecked = False
            items.append(
                (self.itemData(idx, role=role), checked)
            )

        if propagate_all_unchecked_as_checked and all_unchecked:
            items = [
                (value, True)
                for value, checked in items
            ]
        return items

    def get_value(self, role=None):
        if role is None:
            role = self._value_role

        return [
            value
            for value, checked in self.get_value_info(role)
            if checked
        ]

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if (
            event.key() == QtCore.Qt.Key_Down
            and event.modifiers() & QtCore.Qt.AltModifier
        ):
            return self.showPopup()

        if event.key() in self.ignored_keys:
            return event.ignore()

        return super().keyPressEvent(event)

    def _get_checked_idx(self) -> List[int]:
        checked_indexes = []
        for idx in range(self.count()):
            item_type = self.itemData(idx, role=self._item_type_role)
            if item_type is not None and item_type != VALUE_ITEM_TYPE:
                continue

            state = checkstate_int_to_enum(
                self.itemData(idx, role=QtCore.Qt.CheckStateRole)
            )
            if state == QtCore.Qt.Checked:
                checked_indexes.append(idx)
        return checked_indexes

    def _mouse_released_event_handle(
        self, event, current_index, index_flags, state
    ):
        if (
            self._block_mouse_release_timer.isActive()
            or not current_index.isValid()
            or not self.view().isVisible()
            or not self.view().rect().contains(event.pos())
            or not index_flags & QtCore.Qt.ItemIsSelectable
            or not index_flags & QtCore.Qt.ItemIsEnabled
            or not index_flags & QtCore.Qt.ItemIsUserCheckable
        ):
            return None

        if state == QtCore.Qt.Checked:
            return UNCHECKED_INT
        return CHECKED_INT

    def _key_press_event_handler(
        self, event, current_index, index_flags, state
    ):
        # TODO: handle QtCore.Qt.Key_Enter, Key_Return?
        if event.key() != QtCore.Qt.Key_Space:
            return None

        if (
            index_flags & QtCore.Qt.ItemIsUserCheckable
            and index_flags & ITEM_IS_USER_TRISTATE
        ):
            return (checkstate_enum_to_int(state) + 1) % 3

        if index_flags & QtCore.Qt.ItemIsUserCheckable:
            # toggle the current items check state
            if state != QtCore.Qt.Checked:
                return CHECKED_INT
            return UNCHECKED_INT
        return None
