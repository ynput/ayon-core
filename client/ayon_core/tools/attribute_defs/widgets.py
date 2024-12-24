import copy
import typing
from typing import Optional

from qtpy import QtWidgets, QtCore

from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    UnknownDef,
    HiddenDef,
    NumberDef,
    TextDef,
    EnumDef,
    BoolDef,
    FileDef,
    UIDef,
    UISeparatorDef,
    UILabelDef
)
from ayon_core.tools.utils import (
    CustomTextComboBox,
    FocusSpinBox,
    FocusDoubleSpinBox,
    MultiSelectionComboBox,
    set_style_property,
)
from ayon_core.tools.utils import NiceCheckbox

from ._constants import REVERT_TO_DEFAULT_LABEL
from .files_widget import FilesWidget

if typing.TYPE_CHECKING:
    from typing import Union


def create_widget_for_attr_def(
    attr_def: AbstractAttrDef,
    parent: Optional[QtWidgets.QWidget] = None,
    handle_revert_to_default: Optional[bool] = True,
):
    widget = _create_widget_for_attr_def(
        attr_def, parent, handle_revert_to_default
    )
    if not attr_def.visible:
        widget.setVisible(False)

    if not attr_def.enabled:
        widget.setEnabled(False)
    return widget


def _create_widget_for_attr_def(
    attr_def: AbstractAttrDef,
    parent: "Union[QtWidgets.QWidget, None]",
    handle_revert_to_default: bool,
):
    if not isinstance(attr_def, AbstractAttrDef):
        raise TypeError("Unexpected type \"{}\" expected \"{}\"".format(
            str(type(attr_def)), AbstractAttrDef
        ))

    cls = None
    if isinstance(attr_def, NumberDef):
        cls = NumberAttrWidget

    elif isinstance(attr_def, TextDef):
        cls = TextAttrWidget

    elif isinstance(attr_def, EnumDef):
        cls = EnumAttrWidget

    elif isinstance(attr_def, BoolDef):
        cls = BoolAttrWidget

    elif isinstance(attr_def, UnknownDef):
        cls = UnknownAttrWidget

    elif isinstance(attr_def, HiddenDef):
        cls = HiddenAttrWidget

    elif isinstance(attr_def, FileDef):
        cls = FileAttrWidget

    elif isinstance(attr_def, UISeparatorDef):
        cls = SeparatorAttrWidget

    elif isinstance(attr_def, UILabelDef):
        cls = LabelAttrWidget

    if cls is None:
        raise ValueError("Unknown attribute definition \"{}\"".format(
            str(type(attr_def))
        ))

    return cls(attr_def, parent, handle_revert_to_default)


class AttributeDefinitionsLabel(QtWidgets.QLabel):
    """Label related to value attribute definition.

    Label is used to show attribute definition label and to show if value
    is overridden.

    Label can be right-clicked to revert value to default.
    """
    revert_to_default_requested = QtCore.Signal(str)

    def __init__(
        self,
        attr_id: str,
        label: str,
        parent: QtWidgets.QWidget,
    ):
        super().__init__(label, parent)

        self._attr_id = attr_id
        self._overridden = False
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_overridden(self, overridden: bool):
        if self._overridden == overridden:
            return
        self._overridden = overridden
        set_style_property(
            self,
            "overridden",
            "1" if overridden else ""
        )

    def _on_context_menu(self, point: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        action = QtWidgets.QAction(menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self._request_revert_to_default)
        menu.addAction(action)
        menu.exec_(self.mapToGlobal(point))

    def _request_revert_to_default(self):
        self.revert_to_default_requested.emit(self._attr_id)


class AttributeDefinitionsWidget(QtWidgets.QWidget):
    """Create widgets for attribute definitions in grid layout.

    Widget creates input widgets for passed attribute definitions.

    Widget can't handle multiselection values.
    """

    def __init__(self, attr_defs=None, parent=None):
        super().__init__(parent)

        self._widgets_by_id = {}
        self._labels_by_id = {}
        self._current_keys = set()

        self.set_attr_defs(attr_defs)

    def clear_attr_defs(self):
        """Remove all existing widgets and reset layout if needed."""
        self._widgets_by_id = {}
        self._labels_by_id = {}
        self._current_keys = set()

        layout = self.layout()
        if layout is not None:
            if layout.count() == 0:
                return

            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setVisible(False)
                    widget.deleteLater()

            layout.deleteLater()

        new_layout = QtWidgets.QGridLayout()
        new_layout.setColumnStretch(0, 0)
        new_layout.setColumnStretch(1, 1)
        self.setLayout(new_layout)

    def set_attr_defs(self, attr_defs):
        """Replace current attribute definitions with passed."""
        self.clear_attr_defs()
        if attr_defs:
            self.add_attr_defs(attr_defs)

    def add_attr_defs(self, attr_defs):
        """Add attribute definitions to current."""
        layout = self.layout()

        row = 0
        for attr_def in attr_defs:
            if attr_def.is_value_def:
                if attr_def.key in self._current_keys:
                    raise KeyError(
                        "Duplicated key \"{}\"".format(attr_def.key))

                self._current_keys.add(attr_def.key)
            widget = create_widget_for_attr_def(attr_def, self)
            self._widgets_by_id[attr_def.id] = widget

            if not attr_def.visible:
                continue

            expand_cols = 2
            if attr_def.is_value_def and attr_def.is_label_horizontal:
                expand_cols = 1

            col_num = 2 - expand_cols

            if attr_def.is_value_def and attr_def.label:
                label_widget = AttributeDefinitionsLabel(
                    attr_def.id, attr_def.label, self
                )
                label_widget.revert_to_default_requested.connect(
                    self._on_revert_request
                )
                self._labels_by_id[attr_def.id] = label_widget
                tooltip = attr_def.tooltip
                if tooltip:
                    label_widget.setToolTip(tooltip)
                if attr_def.is_label_horizontal:
                    label_widget.setAlignment(
                        QtCore.Qt.AlignRight
                        | QtCore.Qt.AlignVCenter
                    )
                layout.addWidget(
                    label_widget, row, 0, 1, expand_cols
                )
                if not attr_def.is_label_horizontal:
                    row += 1

            if attr_def.is_value_def:
                widget.value_changed.connect(self._on_value_change)

            layout.addWidget(
                widget, row, col_num, 1, expand_cols
            )
            row += 1

    def set_value(self, value):
        new_value = copy.deepcopy(value)
        unused_keys = set(new_value.keys())
        for widget in self._widgets_by_id.values():
            attr_def = widget.attr_def
            if attr_def.key not in new_value:
                continue
            unused_keys.remove(attr_def.key)

            widget_value = new_value[attr_def.key]
            if widget_value is None:
                widget_value = copy.deepcopy(attr_def.default)
            widget.set_value(widget_value)

    def current_value(self):
        output = {}
        for widget in self._widgets_by_id.values():
            attr_def = widget.attr_def
            if not isinstance(attr_def, UIDef):
                output[attr_def.key] = widget.current_value()

        return output

    def _on_revert_request(self, attr_id):
        widget = self._widgets_by_id.get(attr_id)
        if widget is not None:
            widget.set_value(widget.attr_def.default)

    def _on_value_change(self, value, attr_id):
        widget = self._widgets_by_id.get(attr_id)
        if widget is None:
            return
        label = self._labels_by_id.get(attr_id)
        if label is not None:
            label.set_overridden(value != widget.attr_def.default)


class _BaseAttrDefWidget(QtWidgets.QWidget):
    # Type 'object' may not work with older PySide versions
    value_changed = QtCore.Signal(object, str)
    revert_to_default_requested = QtCore.Signal(str)

    def __init__(
        self,
        attr_def: AbstractAttrDef,
        parent: "Union[QtWidgets.QWidget, None]",
        handle_revert_to_default: Optional[bool] = True,
    ):
        super().__init__(parent)

        self.attr_def: AbstractAttrDef = attr_def
        self._handle_revert_to_default: bool = handle_revert_to_default

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_layout = main_layout

        self._ui_init()

    def revert_to_default_value(self):
        if not self.attr_def.is_value_def:
            return

        if self._handle_revert_to_default:
            self.set_value(self.attr_def.default)
        else:
            self.revert_to_default_requested.emit(self.attr_def.id)

    def _ui_init(self):
        raise NotImplementedError(
            "Method '_ui_init' is not implemented. {}".format(
                self.__class__.__name__
            )
        )

    def current_value(self):
        raise NotImplementedError(
            "Method 'current_value' is not implemented. {}".format(
                self.__class__.__name__
            )
        )

    def set_value(self, value, multivalue=False):
        raise NotImplementedError(
            "Method 'set_value' is not implemented. {}".format(
                self.__class__.__name__
            )
        )


class SeparatorAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = QtWidgets.QWidget(self)
        input_widget.setObjectName("Separator")
        input_widget.setMinimumHeight(2)
        input_widget.setMaximumHeight(2)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)


class LabelAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = QtWidgets.QLabel(self)
        label = self.attr_def.label
        if label:
            input_widget.setText(str(label))

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)


class ClickableLineEdit(QtWidgets.QLineEdit):
    clicked = QtCore.Signal()

    def __init__(self, text, parent):
        super().__init__(parent)
        self.setText(text)
        self.setReadOnly(True)

        self._mouse_pressed = False

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._mouse_pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed:
            self._mouse_pressed = False
            if self.rect().contains(event.pos()):
                self.clicked.emit()

        super().mouseReleaseEvent(event)


class NumberAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        decimals = self.attr_def.decimals
        if decimals > 0:
            input_widget = FocusDoubleSpinBox(self)
            input_widget.setDecimals(decimals)
        else:
            input_widget = FocusSpinBox(self)

        # Override context menu event to add revert to default action
        input_widget.contextMenuEvent = self._input_widget_context_event

        if self.attr_def.tooltip:
            input_widget.setToolTip(self.attr_def.tooltip)

        input_widget.setMinimum(self.attr_def.minimum)
        input_widget.setMaximum(self.attr_def.maximum)
        input_widget.setValue(self.attr_def.default)

        input_widget.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        input_line_edit = input_widget.lineEdit()
        input_widget.installEventFilter(self)

        multisel_widget = ClickableLineEdit("< Multiselection >", self)
        multisel_widget.setVisible(False)

        input_widget.valueChanged.connect(self._on_value_change)
        multisel_widget.clicked.connect(self._on_multi_click)

        self._input_widget = input_widget
        self._input_line_edit = input_line_edit
        self._multisel_widget = multisel_widget
        self._last_multivalue = None
        self._multivalue = False

        self.main_layout.addWidget(input_widget, 0)
        self.main_layout.addWidget(multisel_widget, 0)

    def eventFilter(self, obj, event):
        if (
            self._multivalue
            and obj is self._input_widget
            and event.type() == QtCore.QEvent.FocusOut
        ):
            self._set_multiselection_visible(True)
        return False

    def _input_widget_context_event(self, event):
        line_edit = self._input_widget.lineEdit()
        menu = line_edit.createStandardContextMenu()
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        action = QtWidgets.QAction(menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self.revert_to_default_value)
        menu.addAction(action)
        menu.popup(event.globalPos())

    def current_value(self):
        return self._input_widget.value()

    def set_value(self, value, multivalue=False):
        self._last_multivalue = None
        if multivalue:
            set_value = set(value)
            if None in set_value:
                set_value.remove(None)
                set_value.add(self.attr_def.default)

            if len(set_value) > 1:
                self._last_multivalue = next(iter(set_value), None)
                self._set_multiselection_visible(True)
                self._multivalue = True
                return
            value = tuple(set_value)[0]

        self._multivalue = False
        self._set_multiselection_visible(False)

        if self.current_value != value:
            self._input_widget.setValue(value)

    def _on_value_change(self, new_value):
        self._multivalue = False
        self.value_changed.emit(new_value, self.attr_def.id)

    def _on_multi_click(self):
        self._set_multiselection_visible(False, True)

    def _set_multiselection_visible(self, visible, change_focus=False):
        self._input_widget.setVisible(not visible)
        self._multisel_widget.setVisible(visible)
        if visible:
            return

        # Change value once user clicked on the input field
        if self._last_multivalue is None:
            value = self.attr_def.default
        else:
            value = self._last_multivalue
        self._input_widget.blockSignals(True)
        self._input_widget.setValue(value)
        self._input_widget.blockSignals(False)
        if not change_focus:
            return
        # Change focus to input field and move cursor to the end
        self._input_widget.setFocus(QtCore.Qt.MouseFocusReason)
        self._input_line_edit.setCursorPosition(
            len(self._input_line_edit.text())
        )


class TextAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        # TODO Solve how to handle regex
        # self.attr_def.regex

        self.multiline = self.attr_def.multiline
        if self.multiline:
            input_widget = QtWidgets.QPlainTextEdit(self)
        else:
            input_widget = QtWidgets.QLineEdit(self)

        # Override context menu event to add revert to default action
        input_widget.contextMenuEvent = self._input_widget_context_event

        if (
            self.attr_def.placeholder
            and hasattr(input_widget, "setPlaceholderText")
        ):
            input_widget.setPlaceholderText(self.attr_def.placeholder)

        if self.attr_def.tooltip:
            input_widget.setToolTip(self.attr_def.tooltip)

        if self.attr_def.default:
            if self.multiline:
                input_widget.setPlainText(self.attr_def.default)
            else:
                input_widget.setText(self.attr_def.default)

        input_widget.textChanged.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

    def _input_widget_context_event(self, event):
        menu = self._input_widget.createStandardContextMenu()
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        action = QtWidgets.QAction(menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self.revert_to_default_value)
        menu.addAction(action)
        menu.popup(event.globalPos())

    def _on_value_change(self):
        if self.multiline:
            new_value = self._input_widget.toPlainText()
        else:
            new_value = self._input_widget.text()
        self.value_changed.emit(new_value, self.attr_def.id)

    def current_value(self):
        if self.multiline:
            return self._input_widget.toPlainText()
        return self._input_widget.text()

    def set_value(self, value, multivalue=False):
        block_signals = False
        if multivalue:
            set_value = set(value)
            if None in set_value:
                set_value.remove(None)
                set_value.add(self.attr_def.default)

            if len(set_value) == 1:
                value = tuple(set_value)[0]
            else:
                block_signals = True
                value = "< Multiselection >"

        if value != self.current_value():
            if block_signals:
                self._input_widget.blockSignals(True)
            if self.multiline:
                self._input_widget.setPlainText(value)
            else:
                self._input_widget.setText(value)
            if block_signals:
                self._input_widget.blockSignals(False)


class BoolAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = NiceCheckbox(parent=self)
        input_widget.setChecked(self.attr_def.default)

        if self.attr_def.tooltip:
            input_widget.setToolTip(self.attr_def.tooltip)

        input_widget.stateChanged.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)
        self.main_layout.addStretch(1)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        self._menu = QtWidgets.QMenu(self)

        action = QtWidgets.QAction(self._menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self.revert_to_default_value)
        self._menu.addAction(action)

        global_pos = self.mapToGlobal(pos)
        self._menu.exec_(global_pos)

    def _on_value_change(self):
        new_value = self._input_widget.isChecked()
        self.value_changed.emit(new_value, self.attr_def.id)

    def current_value(self):
        return self._input_widget.isChecked()

    def set_value(self, value, multivalue=False):
        if multivalue:
            set_value = set(value)
            if None in set_value:
                set_value.remove(None)
                set_value.add(self.attr_def.default)

            if len(set_value) > 1:
                self._input_widget.blockSignals(True)
                self._input_widget.setCheckState(QtCore.Qt.PartiallyChecked)
                self._input_widget.blockSignals(False)
                return
            value = tuple(set_value)[0]

        if value != self.current_value():
            self._input_widget.setChecked(value)


class EnumAttrWidget(_BaseAttrDefWidget):
    def __init__(self, *args, **kwargs):
        self._multivalue = False
        super().__init__(*args, **kwargs)

    @property
    def multiselection(self):
        return self.attr_def.multiselection

    def _ui_init(self):
        if self.multiselection:
            input_widget = MultiSelectionComboBox(self)

        else:
            input_widget = CustomTextComboBox(self)
            combo_delegate = QtWidgets.QStyledItemDelegate(input_widget)
            input_widget.setItemDelegate(combo_delegate)
            self._combo_delegate = combo_delegate

        if self.attr_def.tooltip:
            input_widget.setToolTip(self.attr_def.tooltip)

        for item in self.attr_def.items:
            input_widget.addItem(item["label"], item["value"])

        idx = input_widget.findData(self.attr_def.default)
        if idx >= 0:
            input_widget.setCurrentIndex(idx)

        if self.multiselection:
            input_widget.value_changed.connect(self._on_value_change)
        else:
            input_widget.currentIndexChanged.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

        input_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        input_widget.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)

        action = QtWidgets.QAction(menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self.revert_to_default_value)
        menu.addAction(action)

        global_pos = self.mapToGlobal(pos)
        menu.exec_(global_pos)

    def _on_value_change(self):
        new_value = self.current_value()
        if self._multivalue:
            self._multivalue = False
            self._input_widget.set_custom_text(None)
        self.value_changed.emit(new_value, self.attr_def.id)

    def current_value(self):
        if self.multiselection:
            return self._input_widget.value()
        idx = self._input_widget.currentIndex()
        return self._input_widget.itemData(idx)

    def _multiselection_multivalue_prep(self, values):
        final = None
        multivalue = False
        for value in values:
            value = set(value)
            if final is None:
                final = value
            elif multivalue or final != value:
                final |= value
                multivalue = True
        return list(final), multivalue

    def set_value(self, value, multivalue=False):
        if multivalue:
            if self.multiselection:
                value, multivalue = self._multiselection_multivalue_prep(
                    value)
            else:
                set_value = set(value)
                if len(set_value) == 1:
                    multivalue = False
                    value = tuple(set_value)[0]

        if self.multiselection:
            self._input_widget.blockSignals(True)
            self._input_widget.set_value(value)
            self._input_widget.blockSignals(False)

        elif not multivalue:
            idx = self._input_widget.findData(value)
            cur_idx = self._input_widget.currentIndex()
            if idx != cur_idx and idx >= 0:
                self._input_widget.setCurrentIndex(idx)

        custom_text = None
        if multivalue:
            custom_text = "< Multiselection >"
        self._input_widget.set_custom_text(custom_text)
        self._multivalue = multivalue


class UnknownAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = QtWidgets.QLabel(self)
        self._value = self.attr_def.default
        input_widget.setText(str(self._value))

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

    def current_value(self):
        raise ValueError(
            "{} can't hold real value.".format(self.__class__.__name__)
        )

    def set_value(self, value, multivalue=False):
        if multivalue:
            set_value = set(value)
            if len(set_value) == 1:
                value = tuple(set_value)[0]
            else:
                value = "< Multiselection >"

        str_value = str(value)
        if str_value != self._value:
            self._value = str_value
            self._input_widget.setText(str_value)


class HiddenAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        self.setVisible(False)
        self._value = self.attr_def.default
        self._multivalue = False

    def setVisible(self, visible):
        if visible:
            visible = False
        super().setVisible(visible)

    def current_value(self):
        if self._multivalue:
            raise ValueError("{} can't output for multivalue.".format(
                self.__class__.__name__
            ))
        return self._value

    def set_value(self, value, multivalue=False):
        self._value = copy.deepcopy(value)
        self._multivalue = multivalue


class FileAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = FilesWidget(
            self.attr_def.single_item,
            self.attr_def.allow_sequences,
            self.attr_def.extensions_label,
            self
        )

        if self.attr_def.tooltip:
            input_widget.setToolTip(self.attr_def.tooltip)

        input_widget.set_filters(
            self.attr_def.folders, self.attr_def.extensions
        )

        input_widget.value_changed.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

        input_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        input_widget.customContextMenuRequested.connect(self._on_context_menu)
        input_widget.revert_requested.connect(self.revert_to_default_value)

    def _on_value_change(self):
        new_value = self.current_value()
        self.value_changed.emit(new_value, self.attr_def.id)

    def _on_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)

        action = QtWidgets.QAction(menu)
        action.setText(REVERT_TO_DEFAULT_LABEL)
        action.triggered.connect(self.revert_to_default_value)
        menu.addAction(action)

        global_pos = self.mapToGlobal(pos)
        menu.exec_(global_pos)

    def current_value(self):
        return self._input_widget.current_value()

    def set_value(self, value, multivalue=False):
        self._input_widget.set_value(value, multivalue)
