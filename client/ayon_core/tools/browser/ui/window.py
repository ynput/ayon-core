from __future__ import annotations

from typing import Optional

from ayon_core.ui.components.container import AYContainer
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline.actions import LoaderActionResult
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.style import load_stylesheet
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.browser.control import LoaderController
from ayon_core.tools.utils import (
    ErrorMessageBox,
    MessageOverlayObject,
    get_qt_icon,
)
from ayon_core.tools.utils.lib import center_window

from .browser_widget import BrowserWidget


class LoadErrorMessageBox(ErrorMessageBox):
    def __init__(self, messages, parent=None):
        self._messages = messages
        super().__init__("Loading failed", parent)

    def _create_top_widget(self, parent_widget):
        label_widget = QtWidgets.QLabel(parent_widget)
        label_widget.setText(
            "<span style='font-size:18pt;'>Failed to load items</span>"
        )
        return label_widget

    def _get_report_data(self):
        report_data = []
        for exc_msg, tb_text, repre, product, version in self._messages:
            report_message = (
                "During load error happened on Product: \"{product}\""
                " Representation: \"{repre}\" Version: {version}"
                "\n\nError message: {message}"
            ).format(
                product=product,
                repre=repre,
                version=version,
                message=exc_msg
            )
            if tb_text:
                report_message += "\n\n{}".format(tb_text)
            report_data.append(report_message)
        return report_data

    def _create_content(self, content_layout):
        item_name_template = (
            "<span style='font-weight:bold;'>Product:</span> {}<br>"
            "<span style='font-weight:bold;'>Version:</span> {}<br>"
            "<span style='font-weight:bold;'>Representation:</span> {}<br>"
        )
        exc_msg_template = "<span style='font-weight:bold'>{}</span>"

        for exc_msg, tb_text, repre, product, version in self._messages:
            line = self._create_line()
            content_layout.addWidget(line)

            item_name = item_name_template.format(product, version, repre)
            item_name_widget = QtWidgets.QLabel(
                item_name.replace("\n", "<br>"), self
            )
            item_name_widget.setWordWrap(True)
            content_layout.addWidget(item_name_widget)

            exc_msg = exc_msg_template.format(exc_msg.replace("\n", "<br>"))
            message_label_widget = QtWidgets.QLabel(exc_msg, self)
            message_label_widget.setWordWrap(True)
            content_layout.addWidget(message_label_widget)

            if tb_text:
                line = self._create_line()
                tb_widget = self._create_traceback_widget(tb_text, self)
                content_layout.addWidget(line)
                content_layout.addWidget(tb_widget)


class BrowserWindow(AYContainer):
    def __init__(
        self,
        controller=None,
        parent=None,
        *,
        use_context: bool = False,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_margin=8,
            layout_spacing=8,
        )

        if controller is None:
            controller = LoaderController()
        self._controller = controller

        subtitle = controller.get_window_subtitle()
        title = "AYON Browser"
        if subtitle:
            title += f" - {subtitle}"
        self.setWindowTitle(title)
        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        overlay_object = MessageOverlayObject(self)

        self.browser_widget = BrowserWidget(controller)
        self.browser_widget.default_view_message.connect(
            self._show_toast_message
        )
        self.add_widget(self.browser_widget)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(1)

        show_timer.timeout.connect(self._on_show_timer)

        controller.register_event_callback(
            "load.finished",
            self._on_load_finished,
        )
        controller.register_event_callback(
            "loader.action.finished",
            self._on_loader_action_finished,
        )

        self._overlay_object = overlay_object

        self._controller = controller
        self._first_show = True
        self._reset_on_show = True
        self._show_counter = 0
        self._show_timer = show_timer
        self._select_context_on_show = use_context

    def select_current_context(self) -> None:
        """Navigate the Browser to the host's current project and folder."""
        self.browser_widget.select_current_context()

    def refresh(self):
        self._reset_on_show = False
        self._controller.reset()

    def showEvent(self, event):
        super().showEvent(event)

        if self._first_show:
            self._on_first_show()

        self._show_timer.start()

    def closeEvent(self, event):
        super().closeEvent(event)

        self._reset_on_show = True

    def _on_first_show(self):
        self._first_show = False
        self.resize(1500, 750)
        self.setStyleSheet(load_stylesheet())
        center_window(self)

    def _on_show_timer(self):
        if self._show_counter < 2:
            self._show_counter += 1
            return

        self._show_counter = 0
        self._show_timer.stop()

        if self._reset_on_show:
            self.refresh()
        if self._select_context_on_show:
            self._select_context_on_show = False
            QtCore.QTimer.singleShot(0, self.select_current_context)
        else:
            QtCore.QTimer.singleShot(
                0,
                self.browser_widget.select_current_context_if_empty,
            )

    def _show_toast_message(
        self,
        message: str,
        success: bool = True,
        message_id: Optional[str] = None,
    ):
        message_type = None
        if not success:
            message_type = "error"

        self._overlay_object.add_message(
            message, message_type, message_id=message_id
        )

    def _on_load_finished(self, event):
        error_info = event["error_info"]
        if not error_info:
            self._controller.invalidate_loaded_containers()
            self.browser_widget.refresh_loaded_state()
            return

        box = LoadErrorMessageBox(error_info, self)
        box.show()

    def _on_loader_action_finished(self, event):
        crashed = event["crashed"]
        if crashed:
            self._show_toast_message(
                "Action failed",
                success=False,
            )
            return

        result: Optional[LoaderActionResult] = event["result"]
        if result is None:
            return

        if result.message:
            self._show_toast_message(
                result.message, result.success
            )

        if result.form is None:
            return

        form = result.form
        dialog = AttributeDefinitionsDialog(
            form.fields,
            title=form.title,
            parent=self,
        )
        if result.form_values:
            dialog.set_values(result.form_values)
        submit_label = form.submit_label
        submit_icon = form.submit_icon
        cancel_label = form.cancel_label
        cancel_icon = form.cancel_icon

        if submit_icon:
            submit_icon = get_qt_icon(submit_icon)
        if cancel_icon:
            cancel_icon = get_qt_icon(cancel_icon)

        if submit_label:
            dialog.set_submit_label(submit_label)
        else:
            dialog.set_submit_visible(False)

        if submit_icon:
            dialog.set_submit_icon(submit_icon)

        if cancel_label:
            dialog.set_cancel_label(cancel_label)
        else:
            dialog.set_cancel_visible(False)

        if cancel_icon:
            dialog.set_cancel_icon(cancel_icon)

        dialog.setMinimumSize(300, 140)
        result = dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return

        form_values = dialog.get_values()
        self._controller.trigger_action_item(
            identifier=event["identifier"],
            project_name=event["project_name"],
            selected_ids=event["selected_ids"],
            selected_entity_type=event["selected_entity_type"],
            options={},
            data=event["data"],
            form_values=form_values,
        )


LoaderWindow = BrowserWindow
