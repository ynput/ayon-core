"""User action callbacks of the template builder window."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ..abstract import ActionResult
from .build_report import BuildReportDialog, STATUS_LABELS
from .constants import EDITOR_PAGE


class WindowActionsMixin:
    """Callbacks that turn window signals into controller actions."""

    def _on_selection_change(self):
        if self._ignore_selection_change:
            return

        scene_identifier = self._placeholders_widget.get_selected_identifier()
        if scene_identifier == self._current_identifier:
            return

        if scene_identifier is None:
            # Clicking empty space in the list must not close the editor.
            if self._current_identifier is not None:
                self._select_silently(self._current_identifier)
            return

        if not self._confirm_discard_changes():
            self._select_silently(self._current_identifier)
            return

        self._show_editor_page(scene_identifier)

    def _on_refresh_request(self):
        if self._busy:
            return
        if not self._confirm_discard_changes():
            return
        self._editor_widget.revert_to_original()
        self._refresh_guarded()

    def _on_run_template_build_request(self):
        if (
            self._pages_widget.currentIndex() == EDITOR_PAGE
            and self._editor_widget.has_unsaved_changes()
        ):
            QtWidgets.QMessageBox.information(
                self,
                "Unsaved changes",
                (
                    "Save or discard the placeholder changes before building"
                    " the template."
                ),
            )
            return

        context_label = self._controller.get_build_context().label
        answer = QtWidgets.QMessageBox.question(
            self,
            "Populate all placeholders?",
            (
                "This will populate all placeholders in the current scene"
                " for {}.\nDo you want to continue?".format(context_label)
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._set_busy(True, "Populating all placeholders...")
        try:
            result = self._controller.run_template_build(
                progress_callback=self._on_build_progress
            )
        except Exception:
            result = None
            self._show_unexpected_error("Failed to run the template build")
        finally:
            self._set_busy(False)

        if result is None:
            return

        # Placeholders may have been removed or changed by the build.
        self._update_placeholders()
        self._update_build_status(result)

        # Show a dialog only when the build itself could not run, per
        #   placeholder failures are shown next to the build button.
        has_results = bool(self._controller.get_last_build_results())
        if not result.success and not has_results:
            self._show_action_error(result)
        elif self._controller.get_build_steps():
            # Always finish a build with its report.
            self._on_show_build_report()

    def _on_open_template_request(self):
        if not self._confirm_discard_changes():
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Open template?",
            (
                "This opens the template of {}:\n{}\n\n"
                "Unsaved changes in the current scene are lost."
                "\nDo you want to continue?"
            ).format(
                self._controller.get_build_context().label,
                self._controller.get_template_path(),
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._set_busy(True, "Opening template...")
        try:
            result = self._controller.open_template()
        except Exception:
            result = None
            self._show_unexpected_error("Failed to open the template")
        finally:
            self._set_busy(False)
        if result is not None:
            self._show_action_error(result)

    def _on_build_from_template_request(self):
        if not self._confirm_discard_changes():
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Build from template?",
            (
                "This imports the template of {} into the current scene"
                " and populates its placeholders:\n{}\n\n"
                "Do you want to continue?"
            ).format(
                self._controller.get_build_context().label,
                self._controller.get_template_path(),
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._set_busy(True, "Building from template...")
        try:
            result = self._controller.build_template(
                progress_callback=self._on_build_progress
            )
        except Exception:
            result = None
            self._show_unexpected_error(
                "Failed to build the scene from the template"
            )
        finally:
            self._set_busy(False)

        if result is None:
            return
        if result.success:
            self._update_build_status(result)
            if self._controller.get_build_steps():
                self._on_show_build_report()
        else:
            self._show_action_error(result)

    def _update_build_status(self, result: ActionResult) -> None:
        """Show the outcome of the last template build.

        Args:
            result (ActionResult): Result of the build action.

        """
        steps = self._controller.get_build_steps()
        if not steps:
            self._build_status_btn.setVisible(False)
            return

        failed = [step for step in steps if step.status == "failed"]
        skipped = [step for step in steps if step.status == "skipped"]
        succeeded = [step for step in steps if step.status == "succeeded"]

        if failed:
            text = "{} of {} failed".format(len(failed), len(steps))
            icon = "error"
        elif skipped and not succeeded:
            text = "{} skipped (not supported)".format(len(skipped))
            icon = "warning"
        elif skipped:
            text = "{} populated, {} skipped".format(
                len(succeeded), len(skipped)
            )
            icon = "check_circle"
        else:
            text = "{} populated".format(len(succeeded))
            icon = "check_circle"

        details = []
        for step in steps:
            status = STATUS_LABELS.get(step.status, step.status.upper())
            details.append(
                "[{}] {} ({})".format(
                    status, step.label, step.scene_identifier
                )
            )
            if step.error:
                details.append(step.error)
        details.append("\nClick to show the build report.")

        self._build_status_btn.setText(text)
        self._build_status_btn.set_icon(icon)
        self._build_status_btn.setToolTip("\n".join(details))
        self._build_status_btn.setVisible(True)

    def _on_context_change_request(self):
        context = self._ask_for_build_context()
        if context is None:
            return
        folder_path, task_name = context
        result = self._controller.set_build_context(folder_path, task_name)
        self._show_action_error(result)

    def _on_context_reset_request(self):
        self._controller.set_build_context(None)

    def _ask_for_build_context(
        self,
    ) -> Optional[tuple[str, Optional[str]]]:
        """Let the user choose a folder and task of the current project.

        Returns:
            Optional[tuple[str, Optional[str]]]: Folder path and task name,
                None when nothing was chosen.

        """
        from ayon_core.tools.context_dialog import ContextDialog

        dialog = ContextDialog(parent=self)
        dialog.setWindowTitle("Test context")
        context_item = self._controller.get_build_context()
        # Keep the project fixed; preselect the current override so opening
        #   the dialog again does not silently reset the reviewed context.
        dialog.set_context(
            self._controller.get_project_name(),
            context_item.folder_path if context_item.is_override else None,
        )
        if not dialog.exec_():
            return None

        context = dialog.get_context()
        if not context.get("initial_context_valid", True):
            QtWidgets.QMessageBox.warning(
                self,
                "Test context",
                (
                    "The selected context no longer exists. Choose another"
                    " folder or reset to the scene context."
                ),
            )
            return None
        folder_path = context.get("folder_path")
        if not folder_path:
            return None
        return folder_path, context.get("task_name")

    def _on_unsaved_changes_change(self, has_changes: bool):
        self._placeholders_widget.set_unsaved_identifier(
            self._editor_widget.get_scene_identifier()
            if has_changes
            else None
        )

    def _on_show_build_report(self):
        dialog = getattr(self, "_build_report_dialog", None)
        if dialog is not None:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return

        dialog = BuildReportDialog(self._controller, parent=self)
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(self._on_build_report_destroyed)
        self._build_report_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_build_report_destroyed(self):
        self._build_report_dialog = None

    def _on_create_request(self, plugin_identifier: Optional[str] = None):
        if not self._controller.is_builder_available():
            return
        if not self._plugin_items:
            return

        # Use the first placeholder type when none is specified
        plugin_item = self._plugin_items[0]
        if plugin_identifier is not None:
            plugin_item = self._get_plugin_item(plugin_identifier)
            if plugin_item is None:
                return

        if not self._confirm_discard_changes():
            return

        self._select_silently(None)
        self._show_create_page(plugin_item)

    def _on_create_cancelled(self):
        if not self._confirm_discard_changes():
            return
        self._select_silently(None)
        self._show_hint_page()

    def _on_create_confirmed(self, plugin_identifier, placeholder_data):
        result = self._controller.create_placeholder(
            plugin_identifier, placeholder_data
        )
        if self._show_action_error(result):
            return

        self._current_identifier = result.scene_identifier
        self._update_placeholders()
        if result.scene_identifier is None:
            self._show_hint_page()
        else:
            self._select_silently(result.scene_identifier)
            self._show_editor_page(result.scene_identifier)

    def _on_save_confirmed(self, scene_identifier, placeholder_data):
        result = self._controller.update_placeholder(
            scene_identifier, placeholder_data
        )
        if self._show_action_error(result):
            return

        new_identifier = result.scene_identifier or scene_identifier
        self._current_identifier = new_identifier
        self._update_placeholders()
        if new_identifier in self._placeholder_items_by_id:
            self._select_silently(new_identifier)
            self._show_editor_page(new_identifier)
        else:
            self._show_hint_page()

    def _on_run_request(self, scene_identifier=None):
        if scene_identifier is None:
            scene_identifier = (
                self._placeholders_widget.get_selected_identifier()
            )
        if scene_identifier is None:
            return

        if (
            self._pages_widget.currentIndex() == EDITOR_PAGE
            and self._editor_widget.has_unsaved_changes()
        ):
            QtWidgets.QMessageBox.information(
                self,
                "Unsaved changes",
                (
                    "Save or discard the placeholder changes before populating"
                    " the placeholder."
                ),
            )
            return

        self._set_busy(True, "Populating placeholder...")
        try:
            result = self._controller.run_placeholder(scene_identifier)
        except Exception:
            result = None
            self._show_unexpected_error("Failed to run the placeholder")
        finally:
            self._set_busy(False)

        if result is None or self._show_action_error(result):
            return

        # The placeholder may have been removed by running it.
        self._update_placeholders()
        self._set_status_text("Placeholder populated")

    def _on_remove_request(self, scene_identifier=None):
        if scene_identifier is None:
            scene_identifier = (
                self._placeholders_widget.get_selected_identifier()
            )
        if scene_identifier is None:
            return

        placeholder_item = self._placeholder_items_by_id.get(scene_identifier)
        label = (
            placeholder_item.label
            if placeholder_item is not None
            else scene_identifier
        )
        plugin_label = (
            placeholder_item.plugin_label
            if placeholder_item is not None
            else ""
        )
        message = "Remove placeholder \"{}\"?".format(label)
        if plugin_label:
            message += "\nType: {}".format(plugin_label)
        message += (
            "\n\nThe placeholder is removed from the scene and cannot be"
            " restored."
        )
        answer = QtWidgets.QMessageBox.question(
            self,
            "Remove placeholder?",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        result = self._controller.delete_placeholder(scene_identifier)
        if self._show_action_error(result):
            return

        self._current_identifier = None
        self._update_placeholders()
        self._show_hint_page()

    def _on_select_in_scene_request(self, scene_identifier=None):
        if scene_identifier is None:
            scene_identifier = (
                self._placeholders_widget.get_selected_identifier()
            )
        if scene_identifier is None:
            return
        result = self._controller.select_placeholder(scene_identifier)
        self._show_action_error(result)
