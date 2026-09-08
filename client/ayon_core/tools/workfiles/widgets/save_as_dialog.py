from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components import (
    AYButton,
    AYCheckBox,
    AYComboBox,
    AYContainer,
    AYLabel,
    AYMenu,
    AYVBoxLayout,
    AYLineEdit,
    AYSpinBox,
    AYTextEdit,
    AYHBoxLayout,
    AYGridLayout,
)


class SaveAsDialog(QtWidgets.QDialog):
    """Save as dialog to define a unique filename inside workdir.

    The filename is calculated in controller where UI sends values from
    dialog inputs.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
    """

    def __init__(self, controller, parent):
        super(SaveAsDialog, self).__init__(parent=parent)
        self.setWindowTitle("Save Workfile As")
        self.setMinimumWidth(330)

        self._controller = controller

        self._folder_id = None
        self._task_id = None
        self._last_version = None
        self._template_key = None
        self._comment_value = None
        self._version_value = None
        self._ext_value = None
        self._filename = None
        self._workdir = None
        self._rootless_workdir = None

        self._result = None

        # Dialog surface to paint the background under other widgets.
        surface = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High_Dark,
            layout_margin=8,
            layout_spacing=4,
        )

        # Inputs widget
        inputs_layout = AYGridLayout(margin=0, spacing=4)

        # Version number input
        version_input = AYSpinBox(
            parent=surface,
            variant=AYSpinBox.Variants.Low,
            minimum=1,
            maximum=9999,
        )

        # Last version checkbox
        last_version_check = AYCheckBox(
            "Next Available Version", parent=surface,
        )
        last_version_check.setChecked(True)
        last_version_check.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Fixed,
        )

        versions_layout = AYHBoxLayout(margin=0, spacing=4)
        versions_layout.addWidget(version_input, 0)
        versions_layout.addWidget(last_version_check, 0)

        # Artist note widget. AYTextEdit does not paint a background of its
        # own, so it is framed the same way as the side panel's note field.
        description_frame = AYContainer(
            surface,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=4,
            layout_spacing=0,
        )
        description_input = AYTextEdit(
            description_frame, variant=AYTextEdit.Variants.Low
        )
        description_input.setPlaceholderText(
            "Provide a note about this workfile.")
        description_input.setMinimumHeight(60)
        description_frame.add_widget(description_input, stretch=1)

        # Preview widget
        preview_widget = AYLabel("Preview filename", parent=surface)
        preview_widget.setWordWrap(True)

        # Subversion input
        subversion_input = AYLineEdit(
            parent=self, variant=AYLineEdit.Variants.Low
        )
        subversion_input.setPlaceholderText("Will be part of filename.")

        subversion_menu_btn = AYButton(
            variant=AYButton.Variants.Surface,
            icon="arrow_drop_down",
            parent=self,
        )
        subversion_menu_btn.setFixedWidth(18)

        subversion_layout = AYHBoxLayout(margin=0, spacing=3)
        subversion_layout.addWidget(subversion_input, 1)
        subversion_layout.addWidget(subversion_menu_btn, 0)

        subversion_menu = AYMenu()
        subversion_menu_btn.setMenu(subversion_menu)

        # Use the same fill as the other inputs so the form rows match
        extension_combobox = AYComboBox(
            parent=surface,
            variant=AYComboBox.Variants.Low,
        )

        version_label = AYLabel("Version:", parent=surface)
        subversion_label = AYLabel("Subversion:", parent=surface)
        extension_label = AYLabel("Extension:", parent=surface)
        preview_label = AYLabel("Preview:", parent=surface)
        description_label = AYLabel("Artist Note:", parent=surface)

        # Btns widget
        btn_ok = AYButton(
            "Save",
            variant=AYButton.Variants.Filled,
            parent=surface,
        )
        btn_cancel = AYButton(
            "Cancel",
            variant=AYButton.Variants.Surface,
            parent=surface,
        )
        btns_layout = AYHBoxLayout(margin=0, spacing=4)
        btns_layout.addWidget(btn_ok, 1)
        btns_layout.addWidget(btn_cancel, 1)

        # Build inputs
        inputs_layout.addWidget(version_label, 0, 0)
        inputs_layout.addLayout(versions_layout, 0, 1)
        inputs_layout.addWidget(subversion_label, 1, 0)
        inputs_layout.addLayout(subversion_layout, 1, 1)
        inputs_layout.addWidget(extension_label, 2, 0)
        inputs_layout.addWidget(extension_combobox, 2, 1)
        inputs_layout.addWidget(preview_label, 3, 0)
        inputs_layout.addWidget(preview_widget, 3, 1)
        inputs_layout.addWidget(description_label, 4, 0, 1, 2)
        inputs_layout.addWidget(description_frame, 5, 0, 1, 2)

        surface.add_layout(inputs_layout, 0)
        surface.add_layout(btns_layout, 0)

        main_layout = AYVBoxLayout(self, margin=0, spacing=0)
        main_layout.addWidget(surface, 1)

        # Signal callback registration
        version_input.valueChanged.connect(self._on_version_spinbox_change)
        last_version_check.stateChanged.connect(
            self._on_version_checkbox_change
        )

        subversion_input.textChanged.connect(self._on_comment_change)
        extension_combobox.currentIndexChanged.connect(
            self._on_extension_change)

        btn_ok.pressed.connect(self._on_ok_pressed)
        btn_cancel.pressed.connect(self._on_cancel_pressed)

        # Store objects
        self._inputs_layout = inputs_layout

        self._btn_ok = btn_ok
        self._btn_cancel = btn_cancel

        self._versions_layout = versions_layout

        self._version_input = version_input
        self._last_version_check = last_version_check

        self._extension_combobox = extension_combobox
        self._subversion_layout = subversion_layout
        self._subversion_input = subversion_input
        self._subversion_menu = subversion_menu
        self._subversion_menu_btn = subversion_menu_btn
        self._preview_widget = preview_widget
        self._description_input = description_input

        self._version_label = version_label
        self._subversion_label = subversion_label
        self._extension_label = extension_label
        self._preview_label = preview_label
        self._description_label = description_label

        # Post init setup

        # Allow "Enter" key to accept the save.
        btn_ok.setDefault(True)

        # Disable version input if last version is checked
        version_input.setEnabled(not last_version_check.isChecked())

        # Force default focus to comment, some hosts didn't automatically
        # apply focus to this line edit (e.g. Houdini)
        subversion_input.setFocus()

    def get_result(self):
        return self._result

    def update_context(self):
        # Add version only if template contains version key
        # - since the version can be padded with "{version:0>4}" we only search
        #   for "{version".
        selected_context = self._controller.get_selected_context()
        folder_id = selected_context["folder_id"]
        task_id = selected_context["task_id"]
        data = self._controller.get_workarea_save_as_data(folder_id, task_id)
        last_version = data["last_version"]
        comment = data["comment"]
        comment_hints = data["comment_hints"]

        template_has_version = data["template_has_version"]
        template_has_comment = data["template_has_comment"]

        self._folder_id = folder_id
        self._task_id = task_id
        self._workdir = data["workdir"]
        self._rootless_workdir = data["rootless_workdir"]
        self._comment_value = data["comment"]
        self._ext_value = data["ext"]
        self._template_key = data["template_key"]
        self._last_version = data["last_version"]

        self._extension_combobox.clear()
        self._extension_combobox.addItems(data["extensions"])

        self._version_input.setValue(last_version)

        vw_idx = self._inputs_layout.indexOf(self._versions_layout)
        self._version_label.setVisible(template_has_version)
        self._version_input.setVisible(template_has_version)
        self._last_version_check.setVisible(template_has_version)
        if template_has_version:
            if vw_idx == -1:
                self._inputs_layout.addWidget(self._version_label, 0, 0)
                self._inputs_layout.addLayout(self._versions_layout, 0, 1)
        elif vw_idx != -1:
            self._inputs_layout.takeAt(vw_idx)
            self._inputs_layout.takeAt(
                self._inputs_layout.indexOf(self._version_label)
            )

        cw_idx = self._inputs_layout.indexOf(self._subversion_layout)
        self._subversion_label.setVisible(template_has_comment)
        self._subversion_input.setVisible(template_has_comment)
        self._subversion_menu_btn.setVisible(template_has_comment)
        if template_has_comment:
            if cw_idx == -1:
                self._inputs_layout.addWidget(self._subversion_label, 1, 0)
                self._inputs_layout.addLayout(self._subversion_layout, 1, 1)
        elif cw_idx != -1:
            self._inputs_layout.takeAt(cw_idx)
            self._inputs_layout.takeAt(
                self._inputs_layout.indexOf(self._subversion_label)
            )

        if template_has_comment:
            self._subversion_input.setText(comment or "")
            self._set_subversion_items(comment_hints)
        self._update_filename()

    def _on_version_spinbox_change(self, value):
        if value == self._version_value:
            return
        self._version_value = value
        if not self._last_version_check.isChecked():
            self._update_filename()

    def _on_version_checkbox_change(self):
        use_last_version = self._last_version_check.isChecked()
        self._version_input.setEnabled(not use_last_version)
        if use_last_version:
            self._version_input.blockSignals(True)
            self._version_input.setValue(self._last_version)
            self._version_input.blockSignals(False)
        self._update_filename()

    def _on_comment_change(self, text):
        if self._comment_value == text:
            return
        self._comment_value = text
        self._update_filename()

    def _on_extension_change(self):
        ext = self._extension_combobox.currentText()
        if ext == self._ext_value:
            return
        self._ext_value = ext
        self._update_filename()

    def _on_subversion_action_clicked(self, action) -> None:
        self._subversion_input.setText(action.text())

    def _set_subversion_items(self, values: list[str] | None) -> None:
        values = values or []

        menu = self._subversion_menu
        button = self._subversion_menu_btn
        button.setEnabled(bool(values))
        if not button.isEnabled():
            return

        # Include an empty string
        values.sort()
        if "" not in values:
            values.insert(0, "")

        # Get and destroy the action group
        group = button.findChild(QtWidgets.QActionGroup)
        if group:
            group.deleteLater()

        # Build new action group
        group = QtWidgets.QActionGroup(button)
        for name in values:
            action = group.addAction(name)
            menu.addAction(action)

        group.triggered.connect(self._on_subversion_action_clicked)

    def _on_ok_pressed(self):
        self._result = {
            "filename": self._filename,
            "workdir": self._workdir,
            "rootless_workdir": self._rootless_workdir,
            "folder_id": self._folder_id,
            "task_id": self._task_id,
            "template_key": self._template_key,
            "version": self._version_value,
            "comment": self._comment_value,
            "description": self._description_input.toPlainText(),
        }
        self.close()

    def _on_cancel_pressed(self):
        self.close()

    def _update_filename(self):
        result = self._controller.fill_workarea_filepath(
            self._folder_id,
            self._task_id,
            self._ext_value,
            self._last_version_check.isChecked(),
            self._version_value,
            self._comment_value,
        )
        self._filename = result.filename
        self._btn_ok.setEnabled(not result.exists)

        color = "green"
        text = result.filename
        if result.exists:
            color = "red"
            text = f'Cannot create "{result.filename}" because file exists!'

        self._preview_widget.set_text_color(color)
        self._preview_widget.setText(text)
