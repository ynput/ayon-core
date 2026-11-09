from __future__ import annotations

from code import InteractiveInterpreter
from qtpy import QtCore, QtWidgets

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.tools.utils.lib import get_qt_icon
from ayon_core.tools.utils.widgets import CodePlainTextEdit


class PythonCodeEditor(CodePlainTextEdit):
    execute_requested = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent, syntax="python")

        self.setObjectName("PythonCodeEditor")

    def keyPressEvent(self, event):
        if (
            event.key() == QtCore.Qt.Key_Return
            and event.modifiers() == QtCore.Qt.ControlModifier
        ):
            self.execute_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class PythonTabWidget(QtWidgets.QWidget):
    add_tab_requested = QtCore.Signal()
    before_execute = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        code_input = PythonCodeEditor(self)

        self.setFocusProxy(code_input)

        add_tab_btn = QtWidgets.QPushButton("Add tab...", self)
        add_tab_btn.setDefault(False)
        add_tab_btn.setToolTip("Add new tab")

        execute_btn = QtWidgets.QPushButton("Execute", self)
        execute_btn.setDefault(False)
        execute_btn.setToolTip("Execute command (Ctrl + Enter)")

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addWidget(add_tab_btn)
        btns_layout.addStretch(1)
        btns_layout.addWidget(execute_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(code_input, 1)
        layout.addLayout(btns_layout, 0)

        add_tab_btn.clicked.connect(self._on_add_tab_clicked)
        execute_btn.clicked.connect(self._on_execute_clicked)
        code_input.execute_requested.connect(self.execute)

        self._code_input = code_input
        self._interpreter = InteractiveInterpreter()

    def _on_add_tab_clicked(self):
        self.add_tab_requested.emit()

    def _on_execute_clicked(self):
        self.execute()

    def get_code(self):
        return self._code_input.toPlainText()

    def set_code(self, code_text):
        self._code_input.setPlainText(code_text)

    def execute(self):
        code_text = self._code_input.toPlainText()
        self.before_execute.emit(code_text)
        self._interpreter.runcode(code_text)


class TabNameDialog(QtWidgets.QDialog):
    default_width = 330
    default_height = 85

    def __init__(self, parent):
        super().__init__(parent)

        self.setWindowTitle("Enter tab name")

        name_label = QtWidgets.QLabel("Tab name:", self)
        name_input = QtWidgets.QLineEdit(self)

        inputs_layout = QtWidgets.QHBoxLayout()
        inputs_layout.addWidget(name_label)
        inputs_layout.addWidget(name_input)

        ok_btn = QtWidgets.QPushButton("Ok", self)
        cancel_btn = QtWidgets.QPushButton("Cancel", self)
        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addStretch(1)
        btns_layout.addWidget(ok_btn)
        btns_layout.addWidget(cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(inputs_layout)
        layout.addStretch(1)
        layout.addLayout(btns_layout)

        ok_btn.clicked.connect(self._on_ok_clicked)
        cancel_btn.clicked.connect(self._on_cancel_clicked)

        self._name_input = name_input
        self._ok_btn = ok_btn
        self._cancel_btn = cancel_btn

        self._result = None

        self.resize(self.default_width, self.default_height)

    def set_tab_name(self, name):
        self._name_input.setText(name)

    def result(self):
        return self._result

    def showEvent(self, event):
        super().showEvent(event)
        btns_width = max(
            self._ok_btn.width(),
            self._cancel_btn.width()
        )

        self._ok_btn.setMinimumWidth(btns_width)
        self._cancel_btn.setMinimumWidth(btns_width)

    def _on_ok_clicked(self):
        self._result = self._name_input.text()
        self.accept()

    def _on_cancel_clicked(self):
        self._result = None
        self.reject()


class OutputTextWidget(QtWidgets.QTextEdit):
    v_max_offset = 4

    def vertical_scroll_at_max(self):
        v_scroll = self.verticalScrollBar()
        return v_scroll.value() > v_scroll.maximum() - self.v_max_offset

    def scroll_to_bottom(self):
        v_scroll = self.verticalScrollBar()
        return v_scroll.setValue(v_scroll.maximum())

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        clear_action = menu.addAction(
            get_qt_icon(MaterialSymbolsIcon("clear_all")), "Clear log"
        )
        clear_action.triggered.connect(self.clear)
        menu.exec_(event.globalPos())


class EnhancedTabBar(QtWidgets.QTabBar):
    double_clicked = QtCore.Signal(QtCore.QPoint)
    right_clicked = QtCore.Signal(QtCore.QPoint)
    mid_clicked = QtCore.Signal(QtCore.QPoint)

    def __init__(self, parent):
        super().__init__(parent)

        self.setDrawBase(False)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(event.globalPos())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.right_clicked.emit(event.globalPos())
            event.accept()
            return

        elif event.button() == QtCore.Qt.MidButton:
            self.mid_clicked.emit(event.globalPos())
            event.accept()

        else:
            super().mouseReleaseEvent(event)
