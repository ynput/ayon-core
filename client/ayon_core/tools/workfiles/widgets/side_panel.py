import datetime
from typing import Optional

from qtpy import QtCore

from ayon_core.ui.components import (
    AYContainer,
    AYButton,
    AYLabel,
    AYTextEdit
)


def file_size_to_string(file_size):
    if not file_size:
        return "N/A"
    size = 0
    size_ending_mapping = {
        "KB": 1024 ** 1,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
    }
    ending = "B"
    for _ending, _size in size_ending_mapping.items():
        if file_size < _size:
            break
        size = file_size / _size
        ending = _ending
    return "{:.2f} {}".format(size, ending)


class SidePanelWidget(AYContainer):
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
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=10,
        )

        # ── Details section ─────────────────────────────────────────
        self.add_widget(AYLabel("Details", rel_text_size=1, parent=self))

        details_form = AYContainer(
            layout=AYContainer.Layout.Form,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=(20, 20),
            parent=self,
        )
        details_form.set_label_alignment(QtCore.Qt.AlignRight)

        size_val = AYLabel("-")
        details_form.add_row(AYLabel("Size:", dim=True), size_val)

        comment_key = AYLabel("Comment:", dim=True)
        comment_val = AYLabel("-")
        comment_val.setWordWrap(True)
        details_form.add_row(comment_key, comment_val)

        created_val = AYLabel("-")
        created_val.setWordWrap(True)
        details_form.add_row(AYLabel("Created:", dim=True), created_val)

        modified_key = AYLabel("Modified:", dim=True)
        modified_val = AYLabel("-")
        modified_val.setWordWrap(True)
        details_form.add_row(modified_key, modified_val)

        self.add_widget(details_form, stretch=1)

        # ── Artist Note section ──────────────────────────────────────
        self.artist_note = AYLabel("Artist Note", rel_text_size=1, parent=self)
        self.add_widget(self.artist_note)

        note_frame = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=4,
            parent=self,
        )
        description_input = AYTextEdit(note_frame)
        btn_description_save = AYButton(
            "Save note", variant=AYButton.Variants.Tonal,
            parent=note_frame,
        )
        note_frame.add_widget(description_input, stretch=1)
        note_frame.add_widget(btn_description_save)
        note_frame._layout.setAlignment(
            btn_description_save, QtCore.Qt.AlignRight
        )

        self.add_widget(note_frame, stretch=1)

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

        self._details_form = details_form
        self._size_val = size_val
        self._created_val = created_val
        self._modified_val = modified_val
        self._comment_val = comment_val
        self._note_frame = note_frame
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
        self.artist_note.setVisible(not published_mode)
        self._note_frame.setVisible(not published_mode)
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

        self._details_form.setEnabled(is_valid)
        self._description_input.setEnabled(is_valid)
        self._btn_description_save.setEnabled(is_valid)

        if not is_valid:
            self._size_val.setText("-")
            self._created_val.setText("-")
            self._modified_val.setText("-")
            self._comment_val.setText("-")
            return

        datetime_format = "%b %d %Y %H:%M:%S"
        user_items_by_name = self._controller.get_user_items_by_name()

        def convert_username(username_v):
            user_item = user_items_by_name.get(username_v)
            if user_item is not None and user_item.full_name:
                return user_item.full_name
            return username_v

        self._size_val.setText(
            file_size_to_string(size_value) if size_value is not None else "-"
        )

        created_parts = []
        if created_by:
            created_parts.append(convert_username(created_by))
        if file_created:
            created_parts.append(
                datetime.datetime.fromtimestamp(file_created).strftime(datetime_format)
            )
        self._created_val.setText("\n".join(created_parts) if created_parts else "-")

        show_modified = bool(updated_by or file_modified)
        if show_modified:
            modified_parts = []
            if updated_by:
                modified_parts.append(convert_username(updated_by))
            if file_modified:
                modified_parts.append(
                    datetime.datetime.fromtimestamp(file_modified).strftime(datetime_format)
                )
            self._modified_val.setText(
                "\n".join(modified_parts) if modified_parts else "-"
            )
        else:
            self._modified_val.setText("-")

        self._comment_val.setText(comment if comment else "-")
