import sys
import json
from typing import Optional

from qtpy import QtWidgets, QtCore

from ayon_core.style import load_stylesheet
from ayon_core.tools.utils import get_ayon_qt_app


class DetailDialog(QtWidgets.QDialog):
    def __init__(self, detail, parent):
        super().__init__(parent)

        self.setWindowTitle("Detail")

        detail_input = QtWidgets.QPlainTextEdit(self)
        detail_input.setPlainText(detail)
        detail_input.setReadOnly(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(detail_input, 1)

    def showEvent(self, event):
        self.resize(600, 400)
        super().showEvent(event)


class ErrorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        message: str,
        detail: Optional[str],
        parent: Optional[QtWidgets.QWidget] = None
    ):
        super().__init__(parent)

        self.setWindowTitle("Preparation failed")
        self.setWindowFlags(
            self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        )

        message_label = QtWidgets.QLabel(self)

        detail_wrapper = QtWidgets.QWidget(self)

        detail_label = QtWidgets.QLabel(detail_wrapper)

        detail_layout = QtWidgets.QVBoxLayout(detail_wrapper)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(detail_label)

        btns_wrapper = QtWidgets.QWidget(self)

        copy_detail_btn = QtWidgets.QPushButton("Copy detail", btns_wrapper)
        show_detail_btn = QtWidgets.QPushButton("Show detail", btns_wrapper)
        confirm_btn = QtWidgets.QPushButton("Close", btns_wrapper)

        btns_layout = QtWidgets.QHBoxLayout(btns_wrapper)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addWidget(copy_detail_btn, 0)
        btns_layout.addWidget(show_detail_btn, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(confirm_btn, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(message_label, 0)
        layout.addWidget(detail_wrapper, 1)
        layout.addWidget(btns_wrapper, 0)

        copy_detail_btn.clicked.connect(self._on_copy_clicked)
        show_detail_btn.clicked.connect(self._on_show_detail_clicked)
        confirm_btn.clicked.connect(self._on_confirm_clicked)

        self._message_label = message_label
        self._detail_wrapper = detail_wrapper
        self._detail_label = detail_label

        self._copy_detail_btn = copy_detail_btn
        self._show_detail_btn = show_detail_btn
        self._confirm_btn = confirm_btn

        self._detail_dialog = None

        self._detail = detail

        self.set_message(message, detail)

    def showEvent(self, event):
        self.setStyleSheet(load_stylesheet())
        self.resize(320, 140)
        super().showEvent(event)

    def set_message(self, message, detail):
        self._message_label.setText(message)
        self._detail = detail

        for widget in (
            self._copy_detail_btn,
            self._show_detail_btn,
        ):
            widget.setVisible(bool(detail))

    def _on_copy_clicked(self):
        if self._detail:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(self._detail)

    def _on_show_detail_clicked(self):
        if self._detail_dialog is None:
            self._detail_dialog = DetailDialog(self._detail, self)
        self._detail_dialog.show()

    def _on_confirm_clicked(self):
        self.accept()


def main():
    json_path = sys.argv[-1]
    with open(json_path, "r") as stream:
        data = json.load(stream)

    message = data["message"]
    detail = data["detail"]
    app = get_ayon_qt_app()
    dialog = ErrorDialog(message, detail)
    dialog.show()
    app.exec_()


if __name__ == "__main__":
    main()
