import datetime
from typing import Optional

from qtpy import QtCore, QtWidgets


def file_size_to_string(file_size):
    if not file_size:
        return "N/A"
    size = 0
    size_ending_mapping = {
        "KB": 1024**1,
        "MB": 1024**2,
        "GB": 1024**3,
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
            "selection.workarea.changed",
            self._on_workarea_selection_change
        )
        controller.register_event_callback(
            "selection.representation.changed",
            self._on_representation_selection_change,
        )

        self._details_input = details_input
        self._description_widget = description_widget
        self._description_input = description_input
        self._btn_description_save = btn_description_save

        self._folder_id = None
        self._task_id = None
        self._filepath = None
        self._rootless_path = None
        self._representation_id = None
        self._orig_description = ""
        self._controller = controller

        self._set_context(False, None, None)

    def set_published_mode(self, published_mode: bool) -> None:
        """Change published mode.

        Args:
            published_mode (bool): Published mode enabled.
        """

        self._description_widget.setVisible(not published_mode)
        # Clear the context when switching modes to avoid showing stale data
        if published_mode:
            self._set_publish_context(
                self._folder_id,
                self._task_id,
                self._representation_id,
            )
        else:
            self._set_workarea_context(
                self._folder_id,
                self._task_id,
                self._rootless_path,
                self._filepath,
            )

    def _on_workarea_selection_change(self, event):
        folder_id = event["folder_id"]
        task_id = event["task_id"]
        filepath = event["path"]
        rootless_path = event["rootless_path"]

        self._set_workarea_context(
            folder_id, task_id, rootless_path, filepath
        )

    def _on_representation_selection_change(self, event):
        folder_id = event["folder_id"]
        task_id = event["task_id"]
        representation_id = event["representation_id"]

        self._set_publish_context(folder_id, task_id, representation_id)

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

    def _set_workarea_context(
        self,
        folder_id: Optional[str],
        task_id: Optional[str],
        rootless_path: Optional[str],
        filepath: Optional[str],
    ) -> None:
        self._rootless_path = rootless_path
        self._filepath = filepath

        workfile_info = None
        # Check if folder, task and file are selected
        if folder_id and task_id and rootless_path:
            workfile_info = self._controller.get_workfile_info(
                folder_id, task_id, rootless_path
            )

        if workfile_info is None:
            self._orig_description = ""
            self._description_input.setPlainText("")
            self._set_context(False, folder_id, task_id)
            return

        self._set_context(
            True,
            folder_id,
            task_id,
            file_created=workfile_info.file_created,
            file_modified=workfile_info.file_modified,
            size_value=workfile_info.file_size,
            created_by=workfile_info.created_by,
            updated_by=workfile_info.updated_by,
        )

        description = workfile_info.description
        self._orig_description = description
        self._description_input.setPlainText(description)

    def _set_publish_context(
        self,
        folder_id: Optional[str],
        task_id: Optional[str],
        representation_id: Optional[str],
    ) -> None:
        self._representation_id = representation_id
        published_workfile_wrap = self._controller.get_published_workfile_info(
            folder_id,
            representation_id,
        )
        info = published_workfile_wrap.info
        comment = published_workfile_wrap.comment
        if info is None:
            self._set_context(False, folder_id, task_id)
            return

        self._set_context(
            True,
            folder_id,
            task_id,
            file_created=info.file_created,
            file_modified=info.file_modified,
            size_value=info.file_size,
            created_by=info.author,
            comment=comment,
        )

    def _set_context(
        self,
        is_valid: bool,
        folder_id: Optional[str],
        task_id: Optional[str],
        *,
        file_created: Optional[int] = None,
        file_modified: Optional[int] = None,
        size_value: Optional[int] = None,
        created_by: Optional[str] = None,
        updated_by: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> None:
        self._folder_id = folder_id
        self._task_id = task_id

        self._details_input.setEnabled(is_valid)
        self._description_input.setEnabled(is_valid)
        self._btn_description_save.setEnabled(is_valid)
        if not is_valid:
            self._details_input.setPlainText("")
            return

        datetime_format = "%b %d %Y %H:%M:%S"
        if file_created:
            file_created = datetime.datetime.fromtimestamp(file_created)

        if file_modified:
            file_modified = datetime.datetime.fromtimestamp(
                file_modified
            )

        user_items_by_name = self._controller.get_user_items_by_name()

        def convert_username(username_v):
            user_item = user_items_by_name.get(username_v)
            if user_item is not None and user_item.full_name:
                return user_item.full_name
            return username_v

        lines = []
        if size_value is not None:
            size_value = file_size_to_string(size_value)
            lines.append(f"<b>Size:</b><br/>{size_value}")

        # Add version comment for published workfiles
        if comment:
            lines.append(f"<b>Comment:</b><br/>{comment}")

        if created_by or file_created:
            lines.append("<b>Created:</b>")
            if created_by:
                lines.append(convert_username(created_by))
            if file_created:
                lines.append(file_created.strftime(datetime_format))

        if updated_by or file_modified:
            lines.append("<b>Modified:</b>")
            if updated_by:
                lines.append(convert_username(updated_by))
            if file_modified:
                lines.append(file_modified.strftime(datetime_format))

        # Set as empty string
        self._details_input.setPlainText("")
        self._details_input.appendHtml("<br/>".join(lines))
