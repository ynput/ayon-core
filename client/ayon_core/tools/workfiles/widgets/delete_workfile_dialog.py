import os

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources


class DeleteWorkfileDialog(QtWidgets.QDialog):
    """Dialog to confirm workfile deletion.

    Args:
        filepath (str): Path to the workfile to be deleted.
        parent (Optional[QtWidgets.QWidget]): Parent widget.
    """

    def __init__(self, filepath, parent=None):
        super(DeleteWorkfileDialog, self).__init__(parent)

        self.setWindowTitle("Delete Workfile")
        self.setModal(True)
        self.resize(400, 150)

        # Set window icon
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        # Create layout
        layout = QtWidgets.QVBoxLayout(self)

        # Warning icon and message
        warning_layout = QtWidgets.QHBoxLayout()

        warning_icon = QtWidgets.QLabel()
        warning_icon.setPixmap(
            QtWidgets.QMessageBox.standardIcon(QtWidgets.QMessageBox.Warning)
        )
        warning_layout.addWidget(warning_icon)

        message_label = QtWidgets.QLabel(
            f"Are you sure you want to delete this workfile?<br/><br/>"
            f"<b>{os.path.basename(filepath)}</b><br/><br/>"
            f"This action cannot be undone and will also remove the "
            f"workfile entry from the AYON database."
        )
        message_label.setWordWrap(True)
        message_label.setTextFormat(QtCore.Qt.RichText)
        warning_layout.addWidget(message_label, 1)

        layout.addLayout(warning_layout)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        delete_button = QtWidgets.QPushButton("Delete")
        delete_button.setDefault(True)
        delete_button.clicked.connect(self.accept)
        # Style delete button as destructive action
        delete_button.setStyleSheet(
            "QPushButton { background-color: #d32f2f; color: white; }"
            "QPushButton:hover { background-color: #b71c1c; }"
        )
        button_layout.addWidget(delete_button)

        layout.addLayout(button_layout)

        # Store filepath for reference
        self._filepath = filepath

    @property
    def filepath(self):
        """Get the filepath of the workfile to be deleted."""
        return self._filepath
