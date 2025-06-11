import sys
import os
import re
import datetime
from qtpy.QtGui import QTextCursor, QColor, QFontDatabase, QFont
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget, QLineEdit, QPushButton, QHBoxLayout
)


class ConsoleStream:
    """Custom stream to redirect stdout and stderr."""
    def __init__(self, console, color):
        self.console = console
        self.color = color

    def write(self, message):
        self.console.append_text(message, self.color)

    def flush(self):
        pass


class ConsoleWidget(QTextEdit):

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    """Custom QTextEdit for displaying console output."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._apply_custom_font()

    def append_text(self, text, color):
        self.setTextColor("#ffffff")  # Default text color
        result = self.ansi_escape.sub('', text)
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        self.insertPlainText(timestamp)
        self.setTextColor(color)
        self.insertPlainText(result)
        self.moveCursor(QTextCursor.End)

    def _apply_custom_font(self):
        """Load and apply a custom font."""
        print(os.path.abspath(__file__))
        font_path = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            "fonts", "LiterationMonoNerdFontMono-Regular.ttf")
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id == -1:
            print("Failed to load font:", font_path)
            return
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        custom_font = QFont(font_family, 10)  # Adjust size as needed
        self.setFont(custom_font)


class ConsoleWindow(QMainWindow):
    """Main window with console and search functionality."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Console Window")
        self.resize(800, 600)

        # Console widget
        self.console = ConsoleWidget()
        # self.console.setStyleSheet("background-color: #1e1e1e; color: white;")

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self.search_text)

        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_console)

        # Layout
        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.clear_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.console)
        main_layout.addLayout(search_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Redirect stdout and stderr
        sys.stdout = ConsoleStream(self.console, QColor("white"))
        sys.stderr = ConsoleStream(self.console, QColor("red"))

    def search_text(self, text):
        """Highlight search results."""
        self.console.moveCursor(QTextCursor.Start)
        cursor = self.console.textCursor()
        format = cursor.charFormat()
        format.setBackground(QColor("yellow"))

        while not cursor.isNull() and not cursor.atEnd():
            cursor = self.console.document().find(text, cursor)
            if not cursor.isNull():
                cursor.mergeCharFormat(format)

    def clear_console(self):
        """Clear the console output."""
        self.console.clear()

    def closeEvent(self, event):
        """Restore stdout and stderr on close."""
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().closeEvent(event)


def load_fonts(font_path: str) -> QFont:
    """Load custom fonts if needed."""
    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id == -1:
        print("Failed to load font:", font_path)
        return None
    font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
    return QFont(font_family)
