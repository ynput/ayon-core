from qtpy import QtWidgets, QtCore

from ayon_core.tools.attribute_defs import create_widget_for_attr_def

from ..constants import INPUTS_LAYOUT_HSPACING, INPUTS_LAYOUT_VSPACING


class PreCreateWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        # Precreate attribute defininitions of Creator
        scroll_area = QtWidgets.QScrollArea(self)
        contet_widget = QtWidgets.QWidget(scroll_area)
        scroll_area.setWidget(contet_widget)
        scroll_area.setWidgetResizable(True)

        attributes_widget = AttributesWidget(contet_widget)
        contet_layout = QtWidgets.QVBoxLayout(contet_widget)
        contet_layout.setContentsMargins(0, 0, 0, 0)
        contet_layout.addWidget(attributes_widget, 0)
        contet_layout.addStretch(1)

        # Widget showed when there are no attribute definitions from creator
        empty_widget = QtWidgets.QWidget(self)
        empty_widget.setVisible(False)

        # Label showed when creator is not selected
        no_creator_label = QtWidgets.QLabel(
            "Creator is not selected",
            empty_widget
        )
        no_creator_label.setWordWrap(True)

        # Creator does not have precreate attributes
        empty_label = QtWidgets.QLabel(
            "This creator has no configurable options",
            empty_widget
        )
        empty_label.setWordWrap(True)
        empty_label.setVisible(False)

        empty_layout = QtWidgets.QVBoxLayout(empty_widget)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addWidget(empty_label, 0, QtCore.Qt.AlignCenter)
        empty_layout.addWidget(no_creator_label, 0, QtCore.Qt.AlignCenter)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area, 1)
        main_layout.addWidget(empty_widget, 1)

        self._scroll_area = scroll_area
        self._empty_widget = empty_widget

        self._empty_label = empty_label
        self._no_creator_label = no_creator_label
        self._attributes_widget = attributes_widget

    def current_value(self):
        return self._attributes_widget.current_value()

    def set_creator_item(self, creator_item):
        attr_defs = []
        creator_selected = False
        if creator_item is not None:
            creator_selected = True
            attr_defs = creator_item.pre_create_attributes_defs

        self._attributes_widget.set_attr_defs(attr_defs)

        attr_defs_available = len(attr_defs) > 0
        self._scroll_area.setVisible(attr_defs_available)
        self._empty_widget.setVisible(not attr_defs_available)

        self._empty_label.setVisible(creator_selected)
        self._no_creator_label.setVisible(not creator_selected)


class AttributesWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(INPUTS_LAYOUT_HSPACING)
        layout.setVerticalSpacing(INPUTS_LAYOUT_VSPACING)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        self._layout = layout

        self._widgets = []

    def current_value(self):
        output = {}
        for widget in self._widgets:
            attr_def = widget.attr_def
            if attr_def.is_value_def:
                output[attr_def.key] = widget.current_value()
        return output

    def clear_attr_defs(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setVisible(False)
                widget.deleteLater()

        self._widgets = []

    def set_attr_defs(self, attr_defs):
        self.clear_attr_defs()

        row = 0
        for attr_def in attr_defs:
            widget = create_widget_for_attr_def(attr_def, self)

            expand_cols = 2
            if attr_def.is_value_def and attr_def.is_label_horizontal:
                expand_cols = 1

            col_num = 2 - expand_cols

            if attr_def.is_value_def and attr_def.label:
                label_widget = QtWidgets.QLabel(attr_def.label, self)
                tooltip = attr_def.tooltip
                if tooltip:
                    label_widget.setToolTip(tooltip)
                if attr_def.is_label_horizontal:
                    label_widget.setAlignment(
                        QtCore.Qt.AlignRight
                        | QtCore.Qt.AlignVCenter
                    )
                self._layout.addWidget(
                    label_widget, row, 0, 1, expand_cols
                )
                if not attr_def.is_label_horizontal:
                    row += 1

            self._layout.addWidget(
                widget, row, col_num, 1, expand_cols
            )
            self._widgets.append(widget)

            row += 1
