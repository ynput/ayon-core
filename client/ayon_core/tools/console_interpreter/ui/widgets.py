from __future__ import annotations

from code import InteractiveInterpreter
import os

from qtpy import QtCore, QtWidgets, QtGui
import pygments.lexers
import pygments.styles
import pygments.token

from ..code_style import AYONStyle


def style_to_formats(
    style: pygments.styles.Style
) -> dict[pygments.token.Token, QtGui.QTextCharFormat]:
    """Convert a Pygments style to a dictionary of Qt formats.

    Args:
        style: The Pygments style to convert.

    Returns:
        token_format = QTextCharFormat for each token in the style.

    """
    formats = {}
    for token, _ in style.styles.items():

        token_style = style.style_for_token(token)
        if not token_style:
            continue

        token_format = QtGui.QTextCharFormat()
        if color := token_style.get("color"):
            color = f"#{color}"
            token_format.setForeground(QtGui.QColor(color))
        if token_style.get("bold"):
            token_format.setFontWeight(QtGui.QFont.Bold)
        if token_style.get("italic"):
            token_format.setFontItalic(True)
        if token_style.get("underline"):
            token_format.setFontUnderline(True)

        formats[token] = token_format

    return formats


class PythonSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document, style_name: str = ""):
        super().__init__(document)
        self.lexer = pygments.lexers.PythonLexer()
        self.style = AYONStyle

        # Allow to override style by environment variable
        override_style_name = os.getenv("AYON_CONSOLE_INTERPRETER_STYLE")
        if override_style_name:
            style = pygments.styles.get_style_by_name(override_style_name)
            if not style:
                all_styles = ", ".join(pygments.styles.get_all_styles())
                raise ValueError(
                    f"'{override_style_name}' not found. "
                    f"Installed styles: {all_styles}"
                )
            self.style = style

        self.formats = style_to_formats(self.style)

    def highlightBlock(self, text: str) -> None:
        index = 0
        for token, value in self.lexer.get_tokens(text):
            length = len(value)

            fmt = self.formats.get(token)
            if fmt:
                self.setFormat(index, length, fmt)

            index += length

    def _format_for_token(self, token):
        if token is None:
            return None
        if token in self.formats:
            return self.formats[token]
        if token.parent:
            return self._format_for_token(token.parent)
        return None


class PythonCodeEditor(QtWidgets.QPlainTextEdit):
    execute_requested = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("PythonCodeEditor")

        self._indent = 4
        self._highlighter = PythonSyntaxHighlighter(self.document())

        if self._highlighter.style:
            background_color = self._highlighter.style.background_color
            if background_color:
                self.setStyleSheet((
                    "QPlainTextEdit {"
                    f"background-color: {background_color};"
                    "}"
                ))

    def _tab_shift_right(self):
        cursor = self.textCursor()
        selected_text = cursor.selectedText()
        if not selected_text:
            cursor.insertText(" " * self._indent)
            return

        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        cursor.setPosition(sel_end)
        end_line = cursor.blockNumber()
        cursor.setPosition(sel_start)
        while True:
            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
            text = cursor.block().text()
            spaces = len(text) - len(text.lstrip(" "))
            new_spaces = spaces % self._indent
            if not new_spaces:
                new_spaces = self._indent

            cursor.insertText(" " * new_spaces)
            if cursor.blockNumber() == end_line:
                break

            cursor.movePosition(QtGui.QTextCursor.NextBlock)

    def _tab_shift_left(self):
        tmp_cursor = self.textCursor()
        sel_start = tmp_cursor.selectionStart()
        sel_end = tmp_cursor.selectionEnd()

        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(sel_end)
        end_line = cursor.blockNumber()
        cursor.setPosition(sel_start)
        while True:
            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
            text = cursor.block().text()
            spaces = len(text) - len(text.lstrip(" "))
            if spaces:
                spaces_to_remove = (spaces % self._indent) or self._indent
                if spaces_to_remove > spaces:
                    spaces_to_remove = spaces

                cursor.setPosition(
                    cursor.position() + spaces_to_remove,
                    QtGui.QTextCursor.KeepAnchor
                )
                cursor.removeSelectedText()

            if cursor.blockNumber() == end_line:
                break

            cursor.movePosition(QtGui.QTextCursor.NextBlock)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Backtab:
            self._tab_shift_left()
            event.accept()
            return

        if event.key() == QtCore.Qt.Key_Tab:
            if event.modifiers() == QtCore.Qt.NoModifier:
                self._tab_shift_right()
            event.accept()
            return

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
