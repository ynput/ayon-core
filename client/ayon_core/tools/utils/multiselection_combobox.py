from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.style import get_objected_colors

from .lib import (
    checkstate_int_to_enum,
    checkstate_enum_to_int,
)
from .constants import (
    CHECKED_INT,
    UNCHECKED_INT,
    ITEM_IS_USER_TRISTATE,
)


class ComboItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    Helper styled delegate (mostly based on existing private Qt's
    delegate used by the QtWidgets.QComboBox). Used to style the popup like a
    list view (e.g windows style).
    """

    def paint(self, painter, option, index):
        option = QtWidgets.QStyleOptionViewItem(option)
        option.showDecorationSelected = True
        super().paint(painter, option, index)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Reserve icon space for items without icon when other items have
        #   icon so labels are aligned
        if (
            not option.features & QtWidgets.QStyleOptionViewItem.HasDecoration
            and self._model_has_icons(index.model())
        ):
            option.features |= QtWidgets.QStyleOptionViewItem.HasDecoration

    @staticmethod
    def _model_has_icons(model):
        for row in range(model.rowCount()):
            icon = model.index(row, 0).data(QtCore.Qt.DecorationRole)
            if icon is not None and not QtGui.QIcon(icon).isNull():
                return True
        return False


class _ChipItem:
    """Painted checked item of 'MultiSelectionComboBox'.

    Args:
        row (int): Row of item in combobox model.
        text (str): Text to paint (can be elided).
        full_text (str): Full text of the item.
        icon (Optional[QtGui.QIcon]): Item icon.
        rect (QtCore.QRectF): Rect of whole chip.
        close_rect (QtCore.QRectF): Rect of close button.

    """
    def __init__(self, row, text, full_text, icon, rect, close_rect):
        self.row = row
        self.text = text
        self.full_text = full_text
        self.icon = icon
        self.rect = rect
        self.close_rect = close_rect

    @property
    def is_elided(self):
        return self.text != self.full_text


class MultiSelectionComboBox(QtWidgets.QComboBox):
    """Multiselection combobox that does not change its height.

    Checked items are painted as chips in a single line within the visible
    area of the widget. Items that do not fit are summarized by '+N'
    indicator (hidden items are listed in its tooltip). Chips are
    highlighted on hover and each chip has close button at its end which
    unchecks the item.

    Args:
        parent (Optional[QtWidgets.QWidget]): Parent widget.
        placeholder (Optional[str]): Text shown when nothing is checked.

    """
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

    top_bottom_padding = 2
    left_right_padding = 3
    left_offset = 4
    top_bottom_margins = 1
    item_spacing = 5
    close_spacing = 4
    close_hit_margin = 2
    # Minimum visible characters of elided item when '+N' is shown
    min_elided_chars = 5

    item_bg_color = QtGui.QColor("#31424e")
    item_hover_bg_color = QtGui.QColor("#3e5463")
    close_hover_bg_color = QtGui.QColor("#5b7486")
    _placeholder_color = None

    def __init__(self, parent=None, placeholder="", **kwargs):
        super().__init__(parent=parent, **kwargs)
        # Use same object name to share styles
        self.setObjectName("MultiSelectionComboBox")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMouseTracking(True)

        delegate = ComboItemDelegate(self)
        self.setItemDelegate(delegate)

        block_mouse_release_timer = QtCore.QTimer(self)
        block_mouse_release_timer.setSingleShot(True)

        self._delegate = delegate
        self._block_mouse_release_timer = block_mouse_release_timer
        self._popup_is_shown = False
        self._initial_mouse_pos = None
        self._placeholder_text = placeholder or ""
        self._custom_text = None

        self._chips = []
        self._overflow_rect = None
        self._overflow_texts = []
        self._hovered_chip_idx = None
        self._hovered_close = False
        self._pressed_close_row = None

    # --- Public API ---
    def get_placeholder_text(self):
        return self._placeholder_text

    def set_placeholder_text(self, text):
        self._placeholder_text = text or ""
        self.update()

    def set_custom_text(self, text):
        self._custom_text = text
        self._update_chips()

    def addItem(self, *args, **kwargs):
        idx = self.count()
        super().addItem(*args, **kwargs)
        self.model().item(idx).setCheckable(True)

    def setItemCheckState(self, index, state):
        self.setItemData(index, state, QtCore.Qt.CheckStateRole)
        self._update_chips()

    def set_value(self, values):
        for idx in range(self.count()):
            value = self.itemData(idx, role=QtCore.Qt.UserRole)
            if value in values:
                check_state = CHECKED_INT
            else:
                check_state = UNCHECKED_INT
            self.setItemData(idx, check_state, QtCore.Qt.CheckStateRole)
        self._update_chips()

    def value(self):
        return [
            self.itemData(row, role=QtCore.Qt.UserRole)
            for row, _, _ in self._get_checked_rows()
        ]

    def checked_items_text(self):
        return [text for _, text, _ in self._get_checked_rows()]

    # --- Qt overrides ---
    def sizeHint(self):
        """Reimplemented to always have height of single line."""
        value = super().sizeHint()
        value.setHeight(
            self._get_chip_height() + (4 * self.top_bottom_margins)
        )
        return value

    def focusInEvent(self, event):
        self.focused_in.emit()
        return super().focusInEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_chips()

    def showPopup(self):
        super().showPopup()
        view = self.view()
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        self._popup_is_shown = True

    def hidePopup(self):
        view = self.view()
        view.removeEventFilter(self)
        view.viewport().removeEventFilter(self)
        self._popup_is_shown = False
        self._initial_mouse_pos = None
        super().hidePopup()
        view.clearFocus()

    def eventFilter(self, obj, event):
        result = self._event_popup_shown(obj, event)
        if result is not None:
            return result
        return super().eventFilter(obj, event)

    def event(self, event):
        """Reimplemented to show tooltips of chips and '+N' indicator."""
        if event.type() == QtCore.QEvent.ToolTip:
            text = self._get_tooltip_at(event.pos())
            if text:
                QtWidgets.QToolTip.showText(event.globalPos(), text, self)
                return True
        return super().event(event)

    def mouseMoveEvent(self, event):
        self._update_hover(event.pos())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._update_hover(None)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Reimplemented.

        Press on close button of a chip does not open the popup.
        """
        if event.button() == QtCore.Qt.LeftButton:
            chip = self._get_close_chip_at(event.pos())
            if chip is not None:
                self._pressed_close_row = chip.row
                event.accept()
                return

        self._popup_is_shown = False
        super().mousePressEvent(event)
        if self._popup_is_shown:
            self._initial_mouse_pos = self.mapToGlobal(event.pos())
            self._block_mouse_release_timer.start(
                QtWidgets.QApplication.doubleClickInterval()
            )

    def mouseReleaseEvent(self, event):
        """Reimplemented.

        Remove item if mouse was pressed and released on the same close
            button.
        """
        pressed_row = self._pressed_close_row
        self._pressed_close_row = None
        if pressed_row is not None:
            event.accept()
            chip = self._get_close_chip_at(event.pos())
            if chip is not None and chip.row == pressed_row:
                self._set_row_checked(pressed_row, False)
            return
        super().mouseReleaseEvent(event)

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

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, option)

        text = None
        if self._custom_text is not None:
            text = self._custom_text
        elif not self._get_checked_rows():
            text = self._placeholder_text

        if text is not None:
            self._paint_placeholder(painter, option, text)
            return

        if not self._chips:
            self._layout_chips()

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setClipRect(self._get_content_rect(option))
        painter.setFont(self.font())

        text_color = self.palette().color(QtGui.QPalette.Text)
        for idx, chip in enumerate(self._chips):
            hovered = idx == self._hovered_chip_idx
            self._paint_chip(
                painter,
                chip,
                hovered,
                hovered and self._hovered_close,
                text_color,
            )

        if self._overflow_rect is not None:
            path = QtGui.QPainterPath()
            path.addRoundedRect(self._overflow_rect, 5, 5)
            painter.fillPath(path, self.item_bg_color)
            painter.setPen(text_color)
            painter.drawText(
                self._overflow_rect,
                QtCore.Qt.AlignCenter,
                f"+{len(self._overflow_texts)}"
            )

    # --- Popup handling ---
    def _event_popup_shown(self, obj, event):
        if not self._popup_is_shown:
            return None

        view = self.view()
        current_index = view.currentIndex()

        if event.type() == QtCore.QEvent.MouseMove:
            if (
                view.isVisible()
                and self._initial_mouse_pos is not None
                and self._block_mouse_release_timer.isActive()
            ):
                diff = obj.mapToGlobal(event.pos()) - self._initial_mouse_pos
                if diff.manhattanLength() > 9:
                    self._block_mouse_release_timer.stop()
            return None

        index_flags = current_index.flags()
        state = checkstate_int_to_enum(
            current_index.data(QtCore.Qt.CheckStateRole)
        )
        new_state = None

        if event.type() == QtCore.QEvent.MouseButtonRelease:
            if (
                self._block_mouse_release_timer.isActive()
                or not current_index.isValid()
                or not view.isVisible()
                or not view.rect().contains(event.pos())
                or not index_flags & QtCore.Qt.ItemIsSelectable
                or not index_flags & QtCore.Qt.ItemIsEnabled
                or not index_flags & QtCore.Qt.ItemIsUserCheckable
            ):
                return None

            if state == QtCore.Qt.Unchecked:
                new_state = CHECKED_INT
            else:
                new_state = UNCHECKED_INT

        elif event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Space:
                if (
                    index_flags & QtCore.Qt.ItemIsUserCheckable
                    and index_flags & ITEM_IS_USER_TRISTATE
                ):
                    new_state = (checkstate_enum_to_int(state) + 1) % 3

                elif index_flags & QtCore.Qt.ItemIsUserCheckable:
                    if state != QtCore.Qt.Checked:
                        new_state = CHECKED_INT
                    else:
                        new_state = UNCHECKED_INT

        if new_state is None:
            return None

        self.model().setData(
            current_index, new_state, QtCore.Qt.CheckStateRole
        )
        view.update(current_index)
        self._update_chips()
        self.value_changed.emit()
        return True

    # --- Chips ---
    def _get_checked_rows(self):
        """Get row, text and icon of checked items.

        Returns:
            list[tuple[int, str, Optional[QtGui.QIcon]]]: Checked items.

        """
        output = []
        for row in range(self.count()):
            state = checkstate_int_to_enum(
                self.itemData(row, role=QtCore.Qt.CheckStateRole)
            )
            if state != QtCore.Qt.Checked:
                continue
            icon = self.itemIcon(row)
            if icon.isNull():
                icon = None
            output.append((row, self.itemText(row), icon))
        return output

    def _set_row_checked(self, row, checked):
        state = CHECKED_INT if checked else UNCHECKED_INT
        self.setItemData(row, state, QtCore.Qt.CheckStateRole)
        self._update_chips()
        self.value_changed.emit()

    def _update_chips(self):
        self._chips = []
        self._overflow_rect = None
        self._overflow_texts = []
        if self._custom_text is None:
            self._layout_chips()

        pos = None
        if self.underMouse():
            pos = self.mapFromGlobal(QtGui.QCursor.pos())
        self._update_hover(pos, force=True)
        self.update()

    def _get_content_rect(self, option=None):
        if option is None:
            option = QtWidgets.QStyleOptionComboBox()
            self.initStyleOption(option)
        btn_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            option,
            QtWidgets.QStyle.SC_ComboBoxArrow,
            self,
        )
        rect = QtCore.QRect(option.rect)
        rect.setWidth(max(0, rect.width() - btn_rect.width()))
        return rect

    def _get_chip_height(self):
        return self.fontMetrics().height() + (2 * self.top_bottom_padding)

    def _get_icon_size(self):
        return self.fontMetrics().height()

    def _get_icon_offset(self, icon):
        if icon is None:
            return 0
        return self._get_icon_size() + self.left_right_padding

    def _get_close_size(self):
        return max(6, int(self.fontMetrics().height() * 0.6))

    def _get_chip_extra_width(self, icon):
        """Width of chip without text."""
        return (
            (2 * self.left_right_padding)
            + self._get_icon_offset(icon)
            + self.close_spacing
            + self._get_close_size()
        )

    def _get_min_text_width(self, text):
        """Minimum width of elided text that is still readable."""
        chars = self.min_elided_chars
        if len(text) <= chars:
            min_text = text
        else:
            min_text = text[:chars] + "\u2026"
        return self.fontMetrics().horizontalAdvance(min_text)

    def _get_overflow_width(self, count):
        return (
            self.fontMetrics().horizontalAdvance(f"+{count}")
            + (4 * self.left_right_padding)
        )

    def _layout_chips(self):
        items = self._get_checked_rows()
        if not items:
            return

        font_metrics = self.fontMetrics()
        content_rect = QtCore.QRectF(self._get_content_rect())
        right_edge = content_rect.right()
        chip_height = self._get_chip_height()
        top = content_rect.top() + (content_rect.height() - chip_height) / 2
        left = content_rect.left() + self.left_offset

        items_count = len(items)
        for idx, (row, text, icon) in enumerate(items):
            # Reserve space for '+N' indicator if there are more items
            hidden_count = items_count - idx - 1
            limit = right_edge
            if hidden_count:
                limit -= (
                    self.item_spacing + self._get_overflow_width(hidden_count)
                )

            extra_width = self._get_chip_extra_width(icon)
            chip_text = text
            width = extra_width + font_metrics.horizontalAdvance(text)
            if left + width > limit:
                if self._chips:
                    break
                text_width = max(0, int(limit - left - extra_width))
                # Elide text of the first chip to make it fit. When there
                #   are more items and the '+N' indicator would leave too
                #   little space for readable text, show only the indicator.
                if hidden_count and text_width < self._get_min_text_width(
                    text
                ):
                    break
                chip_text = font_metrics.elidedText(
                    text, QtCore.Qt.ElideRight, text_width
                )
                width = extra_width + font_metrics.horizontalAdvance(
                    chip_text
                )

            self._chips.append(self._create_chip(
                row, chip_text, text, icon, left, top, width, chip_height
            ))
            left += width + self.item_spacing
            if chip_text != text:
                break

        hidden_items = items[len(self._chips):]
        if hidden_items:
            self._overflow_texts = [text for _, text, _ in hidden_items]
            self._overflow_rect = QtCore.QRectF(
                left,
                top,
                self._get_overflow_width(len(hidden_items)),
                chip_height,
            )

    def _create_chip(
        self, row, text, full_text, icon, left, top, width, height
    ):
        rect = QtCore.QRectF(left, top, width, height)
        close_size = self._get_close_size()
        close_rect = QtCore.QRectF(
            rect.right() - self.left_right_padding - close_size,
            rect.center().y() - (close_size / 2),
            close_size,
            close_size,
        )
        return _ChipItem(row, text, full_text, icon, rect, close_rect)

    # --- Painting ---
    def _paint_placeholder(self, painter, option, text):
        pen = painter.pen()
        pen.setColor(self._get_placeholder_color())
        painter.setPen(pen)

        font = self.font()
        # This is hardcoded point size from styles
        font.setPointSize(10)
        painter.setFont(font)

        label_rect = QtCore.QRect(self._get_content_rect(option))
        label_rect.setLeft(label_rect.left() + self.left_offset)
        painter.drawText(
            label_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            text
        )

    def _paint_chip(self, painter, chip, hovered, close_hovered, text_color):
        bg_color = self.item_hover_bg_color if hovered else self.item_bg_color
        path = QtGui.QPainterPath()
        path.addRoundedRect(chip.rect, 5, 5)
        painter.fillPath(path, bg_color)

        left_x = chip.rect.left() + self.left_right_padding
        if chip.icon is not None:
            icon_size = self._get_icon_size()
            icon_rect = QtCore.QRect(
                int(left_x),
                int(chip.rect.center().y() - (icon_size / 2)),
                icon_size,
                icon_size,
            )
            chip.icon.paint(painter, icon_rect)
            left_x += self._get_icon_offset(chip.icon)

        text_rect = QtCore.QRectF(
            left_x,
            chip.rect.top(),
            max(0.0, chip.close_rect.left() - self.close_spacing - left_x),
            chip.rect.height(),
        )
        painter.setPen(text_color)
        painter.drawText(
            text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, chip.text
        )

        # Close button
        close_color = QtGui.QColor(text_color)
        if close_hovered:
            margin = self.close_hit_margin
            bg_path = QtGui.QPainterPath()
            bg_path.addEllipse(
                chip.close_rect.adjusted(-margin, -margin, margin, margin)
            )
            painter.fillPath(bg_path, self.close_hover_bg_color)
        elif not hovered:
            close_color.setAlpha(140)

        pen = QtGui.QPen(close_color)
        pen.setWidthF(1.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        cross_rect = chip.close_rect.adjusted(2, 2, -2, -2)
        painter.drawLine(cross_rect.topLeft(), cross_rect.bottomRight())
        painter.drawLine(cross_rect.topRight(), cross_rect.bottomLeft())

    # --- Hover and hit testing ---
    def _get_chip_idx_at(self, pos):
        if pos is None:
            return None
        pos = QtCore.QPointF(pos)
        for idx, chip in enumerate(self._chips):
            if chip.rect.contains(pos):
                return idx
        return None

    def _is_pos_on_close(self, chip, pos):
        margin = self.close_hit_margin
        return chip.close_rect.adjusted(
            -margin, -margin, margin, margin
        ).contains(QtCore.QPointF(pos))

    def _get_close_chip_at(self, pos):
        if not self.isEnabled():
            return None
        idx = self._get_chip_idx_at(pos)
        if idx is None:
            return None
        chip = self._chips[idx]
        if self._is_pos_on_close(chip, pos):
            return chip
        return None

    def _update_hover(self, pos, force=False):
        chip_idx = None
        close_hovered = False
        if pos is not None and self.isEnabled():
            chip_idx = self._get_chip_idx_at(pos)
            if chip_idx is not None:
                close_hovered = self._is_pos_on_close(
                    self._chips[chip_idx], pos
                )

        changed = (
            chip_idx != self._hovered_chip_idx
            or close_hovered != self._hovered_close
        )
        if not changed and not force:
            return

        self._hovered_chip_idx = chip_idx
        self._hovered_close = close_hovered
        if close_hovered:
            self.setCursor(QtCore.Qt.PointingHandCursor)
        else:
            self.unsetCursor()
        self.update()

    def _get_tooltip_at(self, pos):
        pos_f = QtCore.QPointF(pos)
        if (
            self._overflow_rect is not None
            and self._overflow_rect.contains(pos_f)
        ):
            return "\n".join(self._overflow_texts)

        chip_idx = self._get_chip_idx_at(pos)
        if chip_idx is None:
            return None
        chip = self._chips[chip_idx]
        if self._is_pos_on_close(chip, pos):
            return f"Remove \"{chip.full_text}\""
        if chip.is_elided:
            return chip.full_text
        return None

    @classmethod
    def _get_placeholder_color(cls):
        if cls._placeholder_color is None:
            color_obj = get_objected_colors("font")
            color = color_obj.get_qcolor()
            color.setAlpha(67)
            cls._placeholder_color = color
        return cls._placeholder_color
