from code import InteractiveInterpreter
import re

from qtpy import QtCore, QtWidgets, QtGui


class PythonSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Define highlighting rules
        self.highlighting_rules = []

        # Keyword format
        keyword_format = QtGui.QTextCharFormat()
        keyword_format.setForeground(QtGui.QColor("#569CD6"))
        keyword_format.setFontWeight(QtGui.QFont.Bold)
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def",
            "del", "elif", "else", "except", "False", "finally", "for",
            "from", "global", "if", "import", "in", "is", "lambda", "None",
            "nonlocal", "not", "or", "pass", "raise", "return", "True",
            "try", "while", "with", "yield", "async", "await"
        ]
        for word in keywords:
            pattern = r"\b" + word + r"\b"
            self.highlighting_rules.append((re.compile(pattern), keyword_format))

        # Built-in functions
        builtin_format = QtGui.QTextCharFormat()
        builtin_format.setForeground(QtGui.QColor("#DCDCAA"))
        builtins = [
            "abs", "all", "any", "bin", "bool", "bytes", "chr", "dict",
            "dir", "enumerate", "filter", "float", "format", "int", "len",
            "list", "map", "max", "min", "open", "print", "range", "repr",
            "round", "set", "sorted", "str", "sum", "tuple", "type", "zip"
        ]
        for word in builtins:
            pattern = r"\b" + word + r"\b"
            self.highlighting_rules.append((re.compile(pattern), builtin_format))

        # String formats
        string_format = QtGui.QTextCharFormat()
        string_format.setForeground(QtGui.QColor("#CE9178"))
        self.highlighting_rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
        self.highlighting_rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))

        # Comment format
        comment_format = QtGui.QTextCharFormat()
        comment_format.setForeground(QtGui.QColor("#6A9955"))
        self.highlighting_rules.append((re.compile(r"#[^\n]*"), comment_format))

        # Number format
        number_format = QtGui.QTextCharFormat()
        number_format.setForeground(QtGui.QColor("#B5CEA8"))
        self.highlighting_rules.append((re.compile(r"\b\d+\.?\d*\b"), number_format))

        # Function/class definition
        function_format = QtGui.QTextCharFormat()
        function_format.setForeground(QtGui.QColor("#DCDCAA"))
        function_format.setFontWeight(QtGui.QFont.Bold)
        self.highlighting_rules.append((re.compile(r"\bdef\s+(\w+)"), function_format))
        self.highlighting_rules.append((re.compile(r"\bclass\s+(\w+)"), function_format))

        # Decorator format
        decorator_format = QtGui.QTextCharFormat()
        decorator_format.setForeground(QtGui.QColor("#4EC9B0"))
        self.highlighting_rules.append((re.compile(r"@\w+"), decorator_format))

    def highlightBlock(self, text):
        for pattern, format_style in self.highlighting_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format_style)


class PythonCodeEditor(QtWidgets.QPlainTextEdit):
    execute_requested = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("PythonCodeEditor")

        self._indent = 4

        self._highlighter = PythonSyntaxHighlighter(self.document())

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
