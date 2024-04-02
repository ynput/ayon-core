from qtpy import QtWidgets

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.tools.utils import PlaceholderLineEdit, FoldersWidget


class FoldersDialogController:
    def __init__(self, controller):
        self._event_system = QueuedEventSystem()
        self._controller = controller

    @property
    def event_system(self):
        return self._event_system

    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self.event_system.add_callback(topic, callback)

    def get_folder_items(self, project_name, sender=None):
        return self._controller.get_folder_items(project_name, sender)

    def set_selected_folder(self, folder_id):
        pass


class FoldersDialog(QtWidgets.QDialog):
    """Dialog to select folder for a context of instance."""

    def __init__(self, controller, parent):
        super(FoldersDialog, self).__init__(parent)
        self.setWindowTitle("Select folder")

        filter_input = PlaceholderLineEdit(self)
        filter_input.setPlaceholderText("Filter folders..")

        folders_controller = FoldersDialogController(controller)
        folders_widget = FoldersWidget(folders_controller, self)
        folders_widget.set_deselectable(True)

        ok_btn = QtWidgets.QPushButton("OK", self)
        cancel_btn = QtWidgets.QPushButton("Cancel", self)

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addStretch(1)
        btns_layout.addWidget(ok_btn)
        btns_layout.addWidget(cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(filter_input, 0)
        layout.addWidget(folders_widget, 1)
        layout.addLayout(btns_layout, 0)

        controller.event_system.add_callback(
            "controller.reset.finished", self._on_controller_reset
        )

        folders_widget.double_clicked.connect(self._on_ok_clicked)
        filter_input.textChanged.connect(self._on_filter_change)
        ok_btn.clicked.connect(self._on_ok_clicked)
        cancel_btn.clicked.connect(self._on_cancel_clicked)

        self._controller = controller
        self._filter_input = filter_input
        self._ok_btn = ok_btn
        self._cancel_btn = cancel_btn

        self._folders_widget = folders_widget

        self._selected_folder_path = None
        # Soft refresh is enabled
        # - reset will happen at all cost if soft reset is enabled
        # - adds ability to call reset on multiple places without repeating
        self._soft_reset_enabled = True

        self._first_show = True
        self._default_height = 500

    def _on_first_show(self):
        center = self.rect().center()
        size = self.size()
        size.setHeight(self._default_height)

        self.resize(size)
        new_pos = self.mapToGlobal(center)
        new_pos.setX(new_pos.x() - int(self.width() / 2))
        new_pos.setY(new_pos.y() - int(self.height() / 2))
        self.move(new_pos)

    def _on_controller_reset(self):
        # Change reset enabled so model is reset on show event
        self._soft_reset_enabled = True

    def showEvent(self, event):
        """Refresh folders widget on show."""
        super(FoldersDialog, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self._on_first_show()
        # Refresh on show
        self.reset(False)

    def reset(self, force=True):
        """Reset widget."""
        if not force and not self._soft_reset_enabled:
            return

        if self._soft_reset_enabled:
            self._soft_reset_enabled = False

        self._folders_widget.set_project_name(self._controller.project_name)

    def _on_filter_change(self, text):
        """Trigger change of filter of folders."""
        self._folders_widget.set_name_filter(text)

    def _on_cancel_clicked(self):
        self.done(0)

    def _on_ok_clicked(self):
        self._selected_folder_path = (
            self._folders_widget.get_selected_folder_path()
        )
        self.done(1)

    def set_selected_folders(self, folder_paths):
        """Change preselected folder before showing the dialog.

        This also resets model and clean filter.
        """
        self.reset(False)
        self._filter_input.setText("")

        folder_id = None
        for folder_path in folder_paths:
            folder_id = self._controller.get_folder_id_from_path(folder_path)
            if folder_id:
                break
        if folder_id:
            self._folders_widget.set_selected_folder(folder_id)

    def get_selected_folder_path(self):
        """Get selected folder path."""
        return self._selected_folder_path
