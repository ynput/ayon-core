import logging
from qtpy import QtWidgets, QtCore

log = logging.getLogger(__name__)


def show_message_dialog(title, message, level=None, parent=None):
    """

    Args:
        title (str): Title of dialog.
        message (str): Message to display.
        level (Literal["info", "warning", "critical"]): Level of dialog.
        parent (Optional[QtCore.QObject]): Parent widget.

    """
    if level is None:
        level = "info"

    if level == "info":
        function = QtWidgets.QMessageBox.information
    elif level == "warning":
        function = QtWidgets.QMessageBox.warning
    elif level == "critical":
        function = QtWidgets.QMessageBox.critical
    else:
        raise ValueError(f"Invalid level: {level}")
    function(parent, title, message)


class ScrollMessageBox(QtWidgets.QDialog):
    """Basic version of scrollable QMessageBox.

    No other existing dialog implementation is scrollable.

    Args:
        icon (QtWidgets.QMessageBox.Icon): Icon to display.
        title (str): Window title.
        messages (list[str]): List of messages.
        cancelable (Optional[bool]): True if Cancel button should be added.

    """
    def __init__(self, icon, title, messages, cancelable=False):
        super(ScrollMessageBox, self).__init__()
        self.setWindowTitle(title)
        self.icon = icon

        self._messages = messages

        self.setWindowFlags(QtCore.Qt.WindowTitleHint)

        layout = QtWidgets.QVBoxLayout(self)

        scroll_widget = QtWidgets.QScrollArea(self)
        scroll_widget.setWidgetResizable(True)
        content_widget = QtWidgets.QWidget(self)
        scroll_widget.setWidget(content_widget)

        message_len = 0
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        for message in messages:
            label_widget = QtWidgets.QLabel(message, content_widget)
            content_layout.addWidget(label_widget)
            message_len = max(message_len, len(message))

        # guess size of scrollable area
        # WARNING: 'desktop' method probably won't work in PySide6
        desktop = QtWidgets.QApplication.desktop()
        max_width = desktop.availableGeometry().width()
        scroll_widget.setMinimumWidth(
            min(max_width, message_len * 6)
        )
        layout.addWidget(scroll_widget)

        buttons = QtWidgets.QDialogButtonBox.Ok
        if cancelable:
            buttons |= QtWidgets.QDialogButtonBox.Cancel

        btn_box = QtWidgets.QDialogButtonBox(buttons)
        btn_box.accepted.connect(self.accept)

        if cancelable:
            btn_box.reject.connect(self.reject)

        btn = QtWidgets.QPushButton("Copy to clipboard")
        btn.clicked.connect(self._on_copy_click)
        btn_box.addButton(btn, QtWidgets.QDialogButtonBox.NoRole)

        layout.addWidget(btn_box)

    def _on_copy_click(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText("\n".join(self._messages))


class SimplePopup(QtWidgets.QDialog):
    """A Popup that moves itself to bottom right of screen on show event.

    The UI contains a message label and a red highlighted button to "show"
    or perform another custom action from this pop-up.

    """

    on_clicked = QtCore.Signal()

    def __init__(self, parent=None, *args, **kwargs):
        super(SimplePopup, self).__init__(parent=parent, *args, **kwargs)

        # Set default title
        self.setWindowTitle("Popup")

        self.setContentsMargins(0, 0, 0, 0)

        message_label = QtWidgets.QLabel("", self)
        message_label.setStyleSheet("""
        QLabel {
            font-size: 12px;
        }
        """)
        confirm_btn = QtWidgets.QPushButton("Show", self)
        confirm_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum,
            QtWidgets.QSizePolicy.Maximum
        )
        confirm_btn.setStyleSheet(
            """QPushButton { background-color: #BB0000 }"""
        )

        # Layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 10)

        # Increase spacing slightly for readability
        layout.setSpacing(10)
        layout.addWidget(message_label)
        layout.addWidget(confirm_btn)

        # Signals
        confirm_btn.clicked.connect(self._on_clicked)

        # Default size
        self.resize(400, 40)

        self._message_label = message_label
        self._confirm_btn = confirm_btn

    def set_message(self, message):
        self._message_label.setText(message)

    def set_button_text(self, text):
        self._confirm_btn.setText(text)

    def setMessage(self, message):
        self.set_message(message)

    def setButtonText(self, text):
        self.set_button_text(text)

    def showEvent(self, event):
        # Position popup based on contents on show event
        geo = self._calculate_window_geometry()
        self.setGeometry(geo)

        return super(SimplePopup, self).showEvent(event)

    def _on_clicked(self):
        """Callback for when the 'show' button is clicked.

        Raises the parent (if any)

        """

        parent = self.parent()
        self.close()

        # Trigger the signal
        self.on_clicked.emit()

        if parent:
            parent.raise_()

    def _calculate_window_geometry(self):
        """Respond to status changes

        On creation, align window with screen bottom right.

        """

        window = self

        width = window.width()
        width = max(width, window.minimumWidth())

        height = window.height()
        height = max(height, window.sizeHint().height())

        try:
            screen = window.screen()
            desktop_geometry = screen.availableGeometry()
        except AttributeError:
            # Backwards compatibility for older Qt versions
            # PySide6 removed QDesktopWidget
            desktop_geometry = QtWidgets.QDesktopWidget().availableGeometry()

        window_geometry = window.geometry()

        screen_width = window_geometry.width()
        screen_height = window_geometry.height()

        # Calculate width and height of system tray
        systray_width = window_geometry.width() - desktop_geometry.width()
        systray_height = window_geometry.height() - desktop_geometry.height()

        padding = 10

        x = screen_width - width
        y = screen_height - height

        x -= systray_width + padding
        y -= systray_height + padding

        return QtCore.QRect(x, y, width, height)


class PopupUpdateKeys(SimplePopup):
    """Simple popup with checkbox."""

    on_clicked_state = QtCore.Signal(bool)

    def __init__(self, parent=None, *args, **kwargs):
        super(PopupUpdateKeys, self).__init__(
            parent=parent, *args, **kwargs
        )

        layout = self.layout()

        # Insert toggle for Update keys
        toggle = QtWidgets.QCheckBox("Update Keys", self)
        layout.insertWidget(1, toggle)

        self.on_clicked.connect(self.emit_click_with_state)

        layout.insertStretch(1, 1)

        self._toggle_checkbox = toggle

    def is_toggle_checked(self):
        return self._toggle_checkbox.isChecked()

    def emit_click_with_state(self):
        """Emit the on_clicked_state signal with the toggled state"""
        checked = self._toggle_checkbox.isChecked()
        self.on_clicked_state.emit(checked)
