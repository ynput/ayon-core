try:
    import commonmark
except Exception:
    commonmark = None

from qtpy import QtWidgets, QtCore

from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend


class HelpButton(QtWidgets.QPushButton):
    """Button used to trigger help dialog."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("CreateDialogHelpButton")
        self.setText("?")


class HelpWidget(QtWidgets.QWidget):
    """Widget showing help for single functionality."""

    def __init__(self, parent):
        super().__init__(parent)

        # TODO add hints what to help with?
        detail_description_input = QtWidgets.QTextEdit(self)
        detail_description_input.setObjectName("CreatorDetailedDescription")
        detail_description_input.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(detail_description_input, 1)

        self._detail_description_input = detail_description_input

        self.set_detailed_text()

    def set_detailed_text(self, text=None):
        if not text:
            text = "We didn't prepare help for this part..."

        if commonmark:
            html = commonmark.commonmark(text)
            self._detail_description_input.setHtml(html)
        elif hasattr(self._detail_description_input, "setMarkdown"):
            self._detail_description_input.setMarkdown(text)
        else:
            self._detail_description_input.setText(text)


class HelpDialog(QtWidgets.QDialog):
    default_width = 530
    default_height = 340

    def __init__(
        self, controller: AbstractPublisherFrontend, parent: QtWidgets.QWidget
    ):
        super().__init__(parent)

        self.setWindowTitle("Help dialog")

        help_content = HelpWidget(self)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addWidget(help_content, 1)

        controller.register_event_callback(
            "show.detailed.help", self._on_help_request
        )

        self._controller: AbstractPublisherFrontend = controller

        self._help_content = help_content

    def _on_help_request(self, event):
        message = event.get("message")
        self.set_detailed_text(message)

    def set_detailed_text(self, text=None):
        self._help_content.set_detailed_text(text)

    def showEvent(self, event):
        super().showEvent(event)
        self.resize(self.default_width, self.default_height)
