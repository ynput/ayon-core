from qtpy import QtWidgets, QtGui, QtCore

from ayon_core.style import load_stylesheet, get_app_icon_path
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    SeparatorWidget,
    set_style_property,
    ProjectsCombobox,
    FoldersWidget,
    TasksWidget,
    NiceCheckbox,
)
from ayon_core.tools.push_to_project.control import (
    PushToContextController,
)


class ErrorDetailDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setWindowTitle("Error detail")
        self.setWindowIcon(QtGui.QIcon(get_app_icon_path()))

        title_label = QtWidgets.QLabel(self)

        sep_1 = SeparatorWidget(parent=self)

        detail_widget = QtWidgets.QTextBrowser(self)
        detail_widget.setReadOnly(True)
        detail_widget.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )

        sep_2 = SeparatorWidget(parent=self)

        btns_widget = QtWidgets.QWidget(self)

        copy_btn = QtWidgets.QPushButton("Copy", btns_widget)
        close_btn = QtWidgets.QPushButton("Close", btns_widget)

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(copy_btn, 0)
        btns_layout.addWidget(close_btn, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(title_label, 0)
        main_layout.addWidget(sep_1, 0)
        main_layout.addWidget(detail_widget, 1)
        main_layout.addWidget(sep_2, 0)
        main_layout.addWidget(btns_widget, 0)

        copy_btn.clicked.connect(self._on_copy_click)
        close_btn.clicked.connect(self._on_close_click)

        self._title_label = title_label
        self._detail_widget = detail_widget

    def set_detail(self, title, detail):
        self._title_label.setText(title)
        self._detail_widget.setText(detail)

    def _on_copy_click(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self._detail_widget.toPlainText())

    def _on_close_click(self):
        self.close()


class PushToContextSelectWindow(QtWidgets.QWidget):
    def __init__(self, controller=None):
        super(PushToContextSelectWindow, self).__init__()
        if controller is None:
            controller = PushToContextController()
        self._controller = controller

        self.setWindowTitle("Push to project (select context)")
        self.setWindowIcon(QtGui.QIcon(get_app_icon_path()))

        main_context_widget = QtWidgets.QWidget(self)

        header_widget = QtWidgets.QWidget(main_context_widget)

        header_label = QtWidgets.QLabel(
            controller.get_source_label(),
            header_widget
        )

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(header_label)

        main_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Horizontal, main_context_widget
        )

        context_widget = QtWidgets.QWidget(main_splitter)

        projects_combobox = ProjectsCombobox(controller, context_widget)
        projects_combobox.set_select_item_visible(True)
        projects_combobox.set_standard_filter_enabled(True)

        context_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Vertical, context_widget
        )

        folders_widget = FoldersWidget(controller, context_splitter)
        folders_widget.set_deselectable(True)
        tasks_widget = TasksWidget(controller, context_splitter)

        context_splitter.addWidget(folders_widget)
        context_splitter.addWidget(tasks_widget)

        context_layout = QtWidgets.QVBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.addWidget(projects_combobox, 0)
        context_layout.addWidget(context_splitter, 1)

        # --- Inputs widget ---
        inputs_widget = QtWidgets.QWidget(main_splitter)

        new_folder_checkbox = NiceCheckbox(True, parent=inputs_widget)

        folder_name_input = PlaceholderLineEdit(inputs_widget)
        folder_name_input.setPlaceholderText("< Name of new folder >")
        folder_name_input.setObjectName("ValidatedLineEdit")
        folder_name_input.setEnabled(new_folder_checkbox.isChecked())

        variant_input = PlaceholderLineEdit(inputs_widget)
        variant_input.setPlaceholderText("< Variant >")
        variant_input.setObjectName("ValidatedLineEdit")

        comment_input = PlaceholderLineEdit(inputs_widget)
        comment_input.setPlaceholderText("< Publish comment >")

        inputs_layout = QtWidgets.QFormLayout(inputs_widget)
        inputs_layout.setContentsMargins(0, 0, 0, 0)
        inputs_layout.addRow("Create new folder", new_folder_checkbox)
        inputs_layout.addRow("New folder name", folder_name_input)
        inputs_layout.addRow("Variant", variant_input)
        inputs_layout.addRow("Comment", comment_input)

        main_splitter.addWidget(context_widget)
        main_splitter.addWidget(inputs_widget)

        # --- Buttons widget ---
        btns_widget = QtWidgets.QWidget(self)
        cancel_btn = QtWidgets.QPushButton("Cancel", btns_widget)
        publish_btn = QtWidgets.QPushButton("Publish", btns_widget)

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(cancel_btn, 0)
        btns_layout.addWidget(publish_btn, 0)

        sep_1 = SeparatorWidget(parent=main_context_widget)
        sep_2 = SeparatorWidget(parent=main_context_widget)
        main_context_layout = QtWidgets.QVBoxLayout(main_context_widget)
        main_context_layout.addWidget(header_widget, 0)
        main_context_layout.addWidget(sep_1, 0)
        main_context_layout.addWidget(main_splitter, 1)
        main_context_layout.addWidget(sep_2, 0)
        main_context_layout.addWidget(btns_widget, 0)

        # NOTE This was added in hurry
        # - should be reorganized and changed styles
        overlay_widget = QtWidgets.QFrame(self)
        overlay_widget.setObjectName("OverlayFrame")

        overlay_label = QtWidgets.QLabel(overlay_widget)
        overlay_label.setAlignment(QtCore.Qt.AlignCenter)
        overlay_label.setWordWrap(True)
        overlay_label.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )

        overlay_btns_widget = QtWidgets.QWidget(overlay_widget)
        overlay_btns_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Add try again button (requires changes in controller)
        overlay_try_btn = QtWidgets.QPushButton(
            "Try again", overlay_btns_widget
        )
        overlay_try_btn.setToolTip(
            "Hide overlay and modify submit information."
        )

        show_detail_btn = QtWidgets.QPushButton(
            "Show error detail", overlay_btns_widget
        )
        show_detail_btn.setToolTip(
            "Show error detail dialog to copy full error."
        )

        overlay_close_btn = QtWidgets.QPushButton(
            "Close", overlay_btns_widget
        )
        overlay_close_btn.setToolTip("Discard changes and close window.")

        overlay_btns_layout = QtWidgets.QHBoxLayout(overlay_btns_widget)
        overlay_btns_layout.setContentsMargins(0, 0, 0, 0)
        overlay_btns_layout.setSpacing(10)
        overlay_btns_layout.addStretch(1)
        overlay_btns_layout.addWidget(overlay_try_btn, 0)
        overlay_btns_layout.addWidget(show_detail_btn, 0)
        overlay_btns_layout.addWidget(overlay_close_btn, 0)
        overlay_btns_layout.addStretch(1)

        overlay_layout = QtWidgets.QVBoxLayout(overlay_widget)
        overlay_layout.addWidget(overlay_label, 0)
        overlay_layout.addWidget(overlay_btns_widget, 0)
        overlay_layout.setAlignment(QtCore.Qt.AlignCenter)

        main_layout = QtWidgets.QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(main_context_widget)
        main_layout.addWidget(overlay_widget)
        main_layout.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        main_layout.setCurrentWidget(main_context_widget)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(0)

        main_thread_timer = QtCore.QTimer()
        main_thread_timer.setInterval(10)

        user_input_changed_timer = QtCore.QTimer()
        user_input_changed_timer.setInterval(200)
        user_input_changed_timer.setSingleShot(True)

        main_thread_timer.timeout.connect(self._on_main_thread_timer)
        show_timer.timeout.connect(self._on_show_timer)
        user_input_changed_timer.timeout.connect(self._on_user_input_timer)
        new_folder_checkbox.stateChanged.connect(self._on_new_folder_check)
        folder_name_input.textChanged.connect(self._on_new_folder_change)
        variant_input.textChanged.connect(self._on_variant_change)
        comment_input.textChanged.connect(self._on_comment_change)

        publish_btn.clicked.connect(self._on_select_click)
        cancel_btn.clicked.connect(self._on_close_click)
        show_detail_btn.clicked.connect(self._on_show_detail_click)
        overlay_close_btn.clicked.connect(self._on_close_click)
        overlay_try_btn.clicked.connect(self._on_try_again_click)

        controller.register_event_callback(
            "new_folder_name.changed",
            self._on_controller_new_folder_change
        )
        controller.register_event_callback(
            "variant.changed", self._on_controller_variant_change
        )
        controller.register_event_callback(
            "comment.changed", self._on_controller_comment_change
        )
        controller.register_event_callback(
            "submission.enabled.changed", self._on_submission_change
        )
        controller.register_event_callback(
            "source.changed", self._on_controller_source_change
        )
        controller.register_event_callback(
            "submit.started", self._on_controller_submit_start
        )
        controller.register_event_callback(
            "submit.finished", self._on_controller_submit_end
        )
        controller.register_event_callback(
            "push.message.added", self._on_push_message
        )

        self._main_layout = main_layout

        self._main_context_widget = main_context_widget

        self._header_label = header_label
        self._main_splitter = main_splitter

        self._projects_combobox = projects_combobox
        self._folders_widget = folders_widget
        self._tasks_widget = tasks_widget

        self._variant_input = variant_input
        self._new_folder_checkbox = new_folder_checkbox
        self._folder_name_input = folder_name_input
        self._comment_input = comment_input

        self._publish_btn = publish_btn

        self._overlay_widget = overlay_widget
        self._show_detail_btn = show_detail_btn
        self._overlay_close_btn = overlay_close_btn
        self._overlay_try_btn = overlay_try_btn
        self._overlay_label = overlay_label

        self._error_detail_dialog = ErrorDetailDialog(self)

        self._user_input_changed_timer = user_input_changed_timer
        # Store current value on input text change
        #   The value is unset when is passed to controller
        # The goal is to have controll over changes happened during user change
        #   in UI and controller auto-changes
        self._new_folder_name_enabled = None
        self._new_folder_name_input_text = None
        self._variant_input_text = None
        self._comment_input_text = None

        self._first_show = True
        self._show_timer = show_timer
        self._show_counter = 0

        self._main_thread_timer = main_thread_timer
        self._main_thread_timer_can_stop = True
        self._last_submit_message = None
        self._process_item_id = None

        self._variant_is_valid = None
        self._folder_is_valid = None

        publish_btn.setEnabled(False)
        show_detail_btn.setVisible(False)
        overlay_close_btn.setVisible(False)
        overlay_try_btn.setVisible(False)

    # Support of public api function of controller
    def set_source(self, project_name, version_id):
        """Set source project and version.

        Call the method on controller.

        Args:
            project_name (Union[str, None]): Name of project.
            version_id (Union[str, None]): Version id.
        """

        self._controller.set_source(project_name, version_id)

    def showEvent(self, event):
        super(PushToContextSelectWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self._on_first_show()

    def refresh(self):
        user_values = self._controller.get_user_values()
        new_folder_name = user_values["new_folder_name"]
        variant = user_values["variant"]
        self._folder_name_input.setText(new_folder_name or "")
        self._variant_input.setText(variant or "")
        self._invalidate_variant(user_values["is_variant_valid"])
        self._invalidate_new_folder_name(
            new_folder_name, user_values["is_new_folder_name_valid"]
        )

        self._projects_combobox.refresh()

    def _on_first_show(self):
        width = 740
        height = 640
        inputs_width = 360
        self.setStyleSheet(load_stylesheet())
        self.resize(width, height)
        self._main_splitter.setSizes([width - inputs_width, inputs_width])
        self._show_timer.start()

    def _on_show_timer(self):
        if self._show_counter < 3:
            self._show_counter += 1
            return
        self._show_timer.stop()

        self._show_counter = 0

        self.refresh()

    def _on_new_folder_check(self):
        self._new_folder_name_enabled = self._new_folder_checkbox.isChecked()
        self._folder_name_input.setEnabled(self._new_folder_name_enabled)
        self._user_input_changed_timer.start()

    def _on_new_folder_change(self, text):
        self._new_folder_name_input_text = text
        self._user_input_changed_timer.start()

    def _on_variant_change(self, text):
        self._variant_input_text = text
        self._user_input_changed_timer.start()

    def _on_comment_change(self, text):
        self._comment_input_text = text
        self._user_input_changed_timer.start()

    def _on_user_input_timer(self):
        folder_name_enabled = self._new_folder_name_enabled
        folder_name = self._new_folder_name_input_text
        if folder_name is not None or folder_name_enabled is not None:
            self._new_folder_name_input_text = None
            self._new_folder_name_enabled = None
            if not self._new_folder_checkbox.isChecked():
                folder_name = None
            elif folder_name is None:
                folder_name = self._folder_name_input.text()
            self._controller.set_user_value_folder_name(folder_name)

        variant = self._variant_input_text
        if variant is not None:
            self._variant_input_text = None
            self._controller.set_user_value_variant(variant)

        comment = self._comment_input_text
        if comment is not None:
            self._comment_input_text = None
            self._controller.set_user_value_comment(comment)

    def _on_controller_new_folder_change(self, event):
        folder_name = event["new_folder_name"]
        if (
            self._new_folder_name_input_text is None
            and folder_name != self._folder_name_input.text()
        ):
            self._folder_name_input.setText(folder_name)

        self._invalidate_new_folder_name(folder_name, event["is_valid"])

    def _on_controller_variant_change(self, event):
        is_valid = event["is_valid"]
        variant = event["variant"]
        if (
            self._variant_input_text is None
            and variant != self._variant_input.text()
        ):
            self._variant_input.setText(variant)

        self._invalidate_variant(is_valid)

    def _on_controller_comment_change(self, event):
        comment = event["comment"]
        if (
            self._comment_input_text is None
            and comment != self._comment_input.text()
        ):
            self._comment_input.setText(comment)

    def _on_controller_source_change(self):
        self._header_label.setText(self._controller.get_source_label())

    def _invalidate_new_folder_name(self, folder_name, is_valid):
        self._tasks_widget.setVisible(folder_name is None)
        if self._folder_is_valid is is_valid:
            return
        self._folder_is_valid = is_valid
        state = ""
        if folder_name is not None:
            state = "valid" if is_valid else "invalid"
        set_style_property(
            self._folder_name_input, "state", state
        )

    def _invalidate_variant(self, is_valid):
        if self._variant_is_valid is is_valid:
            return
        self._variant_is_valid = is_valid
        state = "valid" if is_valid else "invalid"
        set_style_property(self._variant_input, "state", state)

    def _on_submission_change(self, event):
        self._publish_btn.setEnabled(event["enabled"])

    def _on_show_detail_click(self):
        self._error_detail_dialog.show()

    def _on_close_click(self):
        self.close()

    def _on_select_click(self):
        self._process_item_id = self._controller.submit(wait=False)

    def _on_try_again_click(self):
        self._process_item_id = None
        self._last_submit_message = None

        self._error_detail_dialog.close()

        self._overlay_close_btn.setVisible(False)
        self._overlay_try_btn.setVisible(False)
        self._show_detail_btn.setVisible(False)
        self._main_layout.setCurrentWidget(self._main_context_widget)

    def _on_main_thread_timer(self):
        if self._last_submit_message:
            self._overlay_label.setText(self._last_submit_message)
            self._last_submit_message = None

        process_status = self._controller.get_process_item_status(
            self._process_item_id
        )
        push_failed = process_status["failed"]
        fail_traceback = process_status["full_traceback"]
        if self._main_thread_timer_can_stop:
            self._main_thread_timer.stop()
            self._overlay_close_btn.setVisible(True)
            if push_failed:
                self._overlay_try_btn.setVisible(True)
                if fail_traceback:
                    self._show_detail_btn.setVisible(True)

        if push_failed:
            reason = process_status["fail_reason"]
            if fail_traceback:
                message = (
                    "Unhandled error happened."
                    " Check error detail for more information."
                )
                self._error_detail_dialog.set_detail(
                    reason, fail_traceback
                )
            else:
                message = f"Push Failed:\n{reason}"

            self._overlay_label.setText(message)
            set_style_property(self._overlay_close_btn, "state", "error")

        if self._main_thread_timer_can_stop:
            # Join thread in controller
            self._controller.wait_for_process_thread()
            # Reset process item to None
            self._process_item_id = None

    def _on_controller_submit_start(self):
        self._main_thread_timer_can_stop = False
        self._main_thread_timer.start()
        self._main_layout.setCurrentWidget(self._overlay_widget)
        self._overlay_label.setText("Submittion started")

    def _on_controller_submit_end(self):
        self._main_thread_timer_can_stop = True

    def _on_push_message(self, event):
        self._last_submit_message = event["message"]
