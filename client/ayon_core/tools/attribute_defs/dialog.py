from __future__ import annotations

from typing import Optional

from qtpy import QtWidgets, QtGui

from ayon_core.style import load_stylesheet
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.lib import AbstractAttrDef

from .widgets import AttributeDefinitionsWidget


class AttributeDefinitionsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        attr_defs: list[AbstractAttrDef],
        title: Optional[str] = None,
        submit_label: Optional[str] = None,
        cancel_label: Optional[str] = None,
        submit_icon: Optional[QtGui.QIcon] = None,
        cancel_icon: Optional[QtGui.QIcon] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)

        if title:
            self.setWindowTitle(title)

        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setStyleSheet(load_stylesheet())

        attrs_widget = AttributeDefinitionsWidget(attr_defs, self)

        if submit_label is None:
            submit_label = "OK"

        if cancel_label is None:
            cancel_label = "Cancel"

        btns_widget = QtWidgets.QWidget(self)
        cancel_btn = QtWidgets.QPushButton(cancel_label, btns_widget)
        submit_btn = QtWidgets.QPushButton(submit_label, btns_widget)

        if submit_icon is not None:
            submit_btn.setIcon(submit_icon)

        if cancel_icon is not None:
            cancel_btn.setIcon(cancel_icon)

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(submit_btn, 0)
        btns_layout.addWidget(cancel_btn, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(attrs_widget, 0)
        main_layout.addStretch(1)
        main_layout.addWidget(btns_widget, 0)

        submit_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        self._attrs_widget = attrs_widget
        self._submit_btn = submit_btn
        self._cancel_btn = cancel_btn

    def get_values(self):
        return self._attrs_widget.current_value()

    def set_values(self, values):
        self._attrs_widget.set_value(values)

    def set_submit_label(self, text: str):
        self._submit_btn.setText(text)

    def set_submit_icon(self, icon: QtGui.QIcon):
        self._submit_btn.setIcon(icon)

    def set_submit_visible(self, visible: bool):
        self._submit_btn.setVisible(visible)

    def set_cancel_label(self, text: str):
        self._cancel_btn.setText(text)

    def set_cancel_icon(self, icon: QtGui.QIcon):
        self._cancel_btn.setIcon(icon)

    def set_cancel_visible(self, visible: bool):
        self._cancel_btn.setVisible(visible)
