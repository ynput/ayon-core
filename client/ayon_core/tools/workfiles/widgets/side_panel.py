import datetime

from qtpy import QtWidgets, QtCore


def file_size_to_string(file_size):
    if not file_size:
        return "N/A"
    size = 0
    size_ending_mapping = {
        "KB": 1024 ** 1,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3
    }
    ending = "B"
    for _ending, _size in size_ending_mapping.items():
        if file_size < _size:
            break
        size = file_size / _size
        ending = _ending
    return "{:.2f} {}".format(size, ending)


class SidePanelWidget(QtWidgets.QWidget):
    """Details about selected workfile.

    Todos:
        At this moment only shows created and modified date of file
            or its size.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        parent (QtWidgets.QWidget): The parent widget.
    """

    published_workfile_message = (
        "<b>INFO</b>: Opened published workfiles will be stored in"
        " temp directory on your machine. Current temp size: <b>{}</b>."
    )

    def __init__(self, controller, parent):
        super(SidePanelWidget, self).__init__(parent)

        details_label = QtWidgets.QLabel("Details", self)
        details_input = QtWidgets.QPlainTextEdit(self)
        details_input.setReadOnly(True)

        description_widget = QtWidgets.QWidget(self)
        description_label = QtWidgets.QLabel("Artist note", description_widget)
        description_input = QtWidgets.QPlainTextEdit(description_widget)
        btn_description_save = QtWidgets.QPushButton(
            "Save note", description_widget
        )

        description_layout = QtWidgets.QVBoxLayout(description_widget)
        description_layout.setContentsMargins(0, 0, 0, 0)
        description_layout.addWidget(description_label, 0)
        description_layout.addWidget(description_input, 1)
        description_layout.addWidget(
            btn_description_save, 0, alignment=QtCore.Qt.AlignRight
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(details_label, 0)
        main_layout.addWidget(details_input, 1)
        main_layout.addWidget(description_widget, 1)

        description_input.textChanged.connect(self._on_description_change)
        btn_description_save.clicked.connect(self._on_save_click)

        controller.register_event_callback(
            "selection.workarea.changed", self._on_selection_change
        )

        self._details_input = details_input
        self._description_widget = description_widget
        self._description_input = description_input
        self._btn_description_save = btn_description_save

        self._folder_id = None
        self._task_id = None
        self._filepath = None
        self._rootless_path = None
        self._orig_description = ""
        self._controller = controller

        self._set_context(None, None, None, None)

    def set_published_mode(self, published_mode):
        """Change published mode.

        Args:
            published_mode (bool): Published mode enabled.
        """

        self._description_widget.setVisible(not published_mode)

    def _on_selection_change(self, event):
        folder_id = event["folder_id"]
        task_id = event["task_id"]
        filepath = event["path"]
        rootless_path = event["rootless_path"]

        self._set_context(folder_id, task_id, rootless_path, filepath)

    def _on_description_change(self):
        text = self._description_input.toPlainText()
        self._btn_description_save.setEnabled(self._orig_description != text)

    def _on_save_click(self):
        description = self._description_input.toPlainText()
        self._controller.save_workfile_info(
            self._task_id,
            self._rootless_path,
            description=description,
        )
        self._orig_description = description
        self._btn_description_save.setEnabled(False)

    def _set_context(self, folder_id, task_id, rootless_path, filepath):
        workfile_info = None
        # Check if folder, task and file are selected
        if folder_id and task_id and rootless_path:
            workfile_info = self._controller.get_workfile_info(
                folder_id, task_id, rootless_path
            )
        enabled = workfile_info is not None

        self._details_input.setEnabled(enabled)
        self._description_input.setEnabled(enabled)
        self._btn_description_save.setEnabled(enabled)

        self._folder_id = folder_id
        self._task_id = task_id
        self._filepath = filepath
        self._rootless_path = rootless_path

        # Disable inputs and remove texts if any required arguments are
        #   missing
        if not enabled:
            self._orig_description = ""
            self._details_input.setPlainText("")
            self._description_input.setPlainText("")
            return

        description = workfile_info.description
        size_value = file_size_to_string(workfile_info.file_size)

        # Append html string
        datetime_format = "%b %d %Y %H:%M:%S"
        file_created = workfile_info.file_created
        modification_time = workfile_info.file_modified
        if file_created:
            file_created = datetime.datetime.fromtimestamp(file_created)

        if modification_time:
            modification_time = datetime.datetime.fromtimestamp(
                modification_time)

        user_items_by_name = self._controller.get_user_items_by_name()

        def convert_username(username):
            user_item = user_items_by_name.get(username)
            if user_item is not None and user_item.full_name:
                return user_item.full_name
            return username

        created_lines = []
        if workfile_info.created_by:
            created_lines.append(
                convert_username(workfile_info.created_by)
            )
        if file_created:
            created_lines.append(file_created.strftime(datetime_format))

        if created_lines:
            created_lines.insert(0, "<b>Created:</b>")

        modified_lines = []
        if workfile_info.updated_by:
            modified_lines.append(
                convert_username(workfile_info.updated_by)
            )
        if modification_time:
            modified_lines.append(
                modification_time.strftime(datetime_format)
            )
        if modified_lines:
            modified_lines.insert(0, "<b>Modified:</b>")

        lines = (
            "<b>Size:</b>",
            size_value,
            "<br/>".join(created_lines),
            "<br/>".join(modified_lines),
        )
        self._orig_description = description
        self._description_input.setPlainText(description)

        # Set as empty string
        self._details_input.setPlainText("")
        self._details_input.appendHtml("<br/>".join(lines))
