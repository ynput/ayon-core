import os

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources


class DeleteWorkfileDialog(QtWidgets.QDialog):
    """Dialog to confirm workfile deletion.

    Args:
        filepaths (list[str]): Paths to the workfiles to be deleted.
        parent (Optional[QtWidgets.QWidget]): Parent widget.
    """

    def __init__(self, filepaths, parent=None):
        super(DeleteWorkfileDialog, self).__init__(parent)

        if isinstance(filepaths, str):
            filepaths = [filepaths]
        self._filepaths = list(filepaths)

        self.setWindowTitle("Delete Workfile(s)")
        self.setModal(True)
        self.resize(450, 300)

        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        layout = QtWidgets.QVBoxLayout(self)

        warning_layout = QtWidgets.QHBoxLayout()
        warning_icon = QtWidgets.QLabel()
        warning_icon.setPixmap(
            QtWidgets.QMessageBox.standardIcon(QtWidgets.QMessageBox.Warning)
        )
        warning_layout.addWidget(warning_icon)

        message_label = QtWidgets.QLabel(
            "Are you sure you want to delete the following workfile(s)? "
            "This action cannot be undone and will also remove the "
            "workfile entries from the AYON database."
        )
        message_label.setWordWrap(True)
        message_label.setTextFormat(QtCore.Qt.RichText)
        warning_layout.addWidget(message_label, 1)
        layout.addLayout(warning_layout)

        file_list = QtWidgets.QListWidget()
        file_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for fp in self._filepaths:
            file_list.addItem(os.path.basename(fp))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(file_list)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setMinimumHeight(min(200, 24 * len(self._filepaths) + 4))
        scroll.setMaximumHeight(280)
        layout.addWidget(scroll)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        delete_button = QtWidgets.QPushButton("Delete")
        delete_button.setDefault(True)
        delete_button.clicked.connect(self.accept)
        delete_button.setStyleSheet(
            "QPushButton { background-color: #d32f2f; color: white; }"
            "QPushButton:hover { background-color: #b71c1c; }"
        )
        button_layout.addWidget(delete_button)
        layout.addLayout(button_layout)

    @property
    def filepaths(self):
        """List of filepaths to be deleted."""
        return self._filepaths
