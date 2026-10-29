"""Main window of workfile template builder tool."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources, style
from ayon_core.ui.components import AYContainer

from ..abstract import (
    PLACEHOLDERS_REFRESHED_TOPIC,
    AbstractTemplateBuilderController,
    ActionResult,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from .editor_widget import PlaceholderEditorWidget, PlaceholderHintWidget
from .placeholders_widget import PlaceholdersWidget

HINT_PAGE = 0
EDITOR_PAGE = 1


class WorkfileTemplateBuilderWindow(AYContainer):
    """Manage placeholders of a workfile template.

    Args:
        controller (AbstractTemplateBuilderController): Backend of the tool.
        parent (Optional[QtWidgets.QWidget]): Parent widget.

    """

    def __init__(
        self,
        controller: AbstractTemplateBuilderController,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_margin=8,
        )

        self.setWindowTitle("AYON Workfile Template Builder - {}".format(
            controller.get_host_name()
        ))
        self.setWindowIcon(QtGui.QIcon(resources.get_ayon_icon_filepath()))
        self.setObjectName("WorkfileTemplateBuilderWindow")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        placeholders_widget = PlaceholdersWidget(self)

        pages_widget = QtWidgets.QStackedWidget(self)
        hint_widget = PlaceholderHintWidget(pages_widget)
        editor_widget = PlaceholderEditorWidget(controller, pages_widget)
        pages_widget.addWidget(hint_widget)
        pages_widget.addWidget(editor_widget)

        content_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_margin=6,
        )
        content_widget.add_widget(pages_widget, stretch=1)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.addWidget(placeholders_widget)
        splitter.addWidget(content_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 680])

        self.add_widget(splitter, stretch=1)

        placeholders_widget.selection_changed.connect(
            self._on_selection_change
        )
        placeholders_widget.create_requested.connect(self._on_create_request)
        placeholders_widget.delete_requested.connect(self._on_delete_request)
        placeholders_widget.select_in_scene_requested.connect(
            self._on_select_in_scene_request
        )
        placeholders_widget.refresh_requested.connect(self._on_refresh_request)
        hint_widget.create_requested.connect(self._on_create_request)
        editor_widget.create_requested.connect(self._on_create_confirmed)
        editor_widget.save_requested.connect(self._on_save_confirmed)
        editor_widget.cancel_requested.connect(self._on_create_cancelled)

        controller.register_event_callback(
            PLACEHOLDERS_REFRESHED_TOPIC, self._on_placeholders_refreshed
        )

        self._controller = controller
        self._placeholders_widget = placeholders_widget
        self._pages_widget = pages_widget
        self._hint_widget = hint_widget
        self._editor_widget = editor_widget

        self._first_show = True
        self._ignore_selection_change = False
        self._current_identifier: Optional[str] = None
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._placeholder_items_by_id: dict[str, PlaceholderItemInfo] = {}

        self.resize(1020, 620)

    # --- Qt overrides -------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())
            self.refresh()

    # --- Public API ---------------------------------------------------
    def refresh(self):
        """Collect placeholders from the scene and update the UI."""
        self._controller.reset()

    # --- Implementation -----------------------------------------------
    def _on_placeholders_refreshed(self):
        self._update_placeholders()

    def _update_placeholders(self):
        self._plugin_items = self._controller.get_placeholder_plugin_items()
        placeholder_items = self._controller.get_placeholder_items()
        self._placeholder_items_by_id = {
            item.scene_identifier: item for item in placeholder_items
        }

        self._ignore_selection_change = True
        self._placeholders_widget.set_plugin_items(self._plugin_items)
        self._placeholders_widget.set_placeholder_items(placeholder_items)
        self._placeholders_widget.select_identifier(self._current_identifier)
        self._ignore_selection_change = False

        # Placeholder that was edited may be gone from the scene
        if self._current_identifier not in self._placeholder_items_by_id:
            self._current_identifier = None

        if self._pages_widget.currentIndex() == EDITOR_PAGE:
            editor_identifier = self._editor_widget.get_scene_identifier()
            if (
                editor_identifier is not None
                and editor_identifier not in self._placeholder_items_by_id
            ):
                self._show_hint_page()
                return

        if self._pages_widget.currentIndex() == HINT_PAGE:
            self._update_hint_message()

    def _update_hint_message(self):
        if not self._controller.is_builder_available():
            self._hint_widget.set_message(
                "Template build is not available",
                (
                    "Host \"{}\" does not implement workfile template"
                    " build.".format(self._controller.get_host_name())
                ),
                create_enabled=False,
            )
            return

        if not self._plugin_items:
            self._hint_widget.set_message(
                "No placeholder types available",
                (
                    "Host \"{}\" does not have any placeholder plugins"
                    " registered.".format(self._controller.get_host_name())
                ),
                create_enabled=False,
            )
            return

        if not self._placeholder_items_by_id:
            self._hint_widget.set_message(
                "No placeholders in this workfile",
                (
                    "Placeholders describe what should happen when this"
                    " template is built - which products are loaded and"
                    " which publish instances are created."
                    "\n\nAdd your first placeholder to get started."
                ),
            )
            return

        self._hint_widget.set_message(
            "Select a placeholder",
            (
                "Pick a placeholder on the left to change its options and"
                " see what it would do, or add a new one."
            ),
        )

    def _show_hint_page(self):
        self._current_identifier = None
        self._update_hint_message()
        self._pages_widget.setCurrentIndex(HINT_PAGE)

    def _show_editor_page(self, scene_identifier):
        placeholder_item = self._placeholder_items_by_id.get(scene_identifier)
        if placeholder_item is None:
            self._show_hint_page()
            return

        self._current_identifier = scene_identifier
        self._editor_widget.set_edit_mode(placeholder_item)
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)

    def _show_create_page(self):
        self._current_identifier = None
        self._editor_widget.set_create_mode(self._plugin_items)
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)

    def _select_silently(self, scene_identifier):
        self._ignore_selection_change = True
        self._placeholders_widget.select_identifier(scene_identifier)
        self._ignore_selection_change = False

    def _confirm_discard_changes(self):
        """Ask the user before losing changed options.

        Returns:
            bool: Changes can be discarded.

        """
        if self._pages_widget.currentIndex() != EDITOR_PAGE:
            return True
        if not self._editor_widget.has_unsaved_changes():
            return True

        answer = QtWidgets.QMessageBox.question(
            self,
            "Discard changes?",
            (
                "Placeholder options were changed and are not saved."
                "\nDo you want to discard the changes?"
            ),
            QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        return answer == QtWidgets.QMessageBox.Discard

    def _show_action_error(self, result: ActionResult) -> bool:
        """Show a message box when an action failed.

        Args:
            result (ActionResult): Result of the action.

        Returns:
            bool: Action failed.

        """
        if result.success:
            return False

        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle("Workfile Template Builder")
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setText(result.error_title or "Action failed")
        if result.error_detail:
            dialog.setDetailedText(result.error_detail)
        dialog.exec_()
        return True

    # --- Callbacks ----------------------------------------------------
    def _on_selection_change(self):
        if self._ignore_selection_change:
            return

        scene_identifier = self._placeholders_widget.get_selected_identifier()
        if scene_identifier == self._current_identifier:
            return

        if not self._confirm_discard_changes():
            self._select_silently(self._current_identifier)
            return

        if scene_identifier is None:
            self._show_hint_page()
        else:
            self._show_editor_page(scene_identifier)

    def _on_refresh_request(self):
        if not self._confirm_discard_changes():
            return
        self.refresh()

    def _on_create_request(self):
        if not self._controller.is_builder_available():
            return
        if not self._plugin_items:
            return
        if not self._confirm_discard_changes():
            return

        self._select_silently(None)
        self._show_create_page()

    def _on_create_cancelled(self):
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

        self._update_placeholders()
        self._show_editor_page(scene_identifier)

    def _on_delete_request(self):
        scene_identifier = self._placeholders_widget.get_selected_identifier()
        if scene_identifier is None:
            return

        placeholder_item = self._placeholder_items_by_id.get(scene_identifier)
        label = scene_identifier
        if placeholder_item is not None:
            label = placeholder_item.label

        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete placeholder?",
            (
                "Are you sure you want to delete placeholder"
                " \"{}\" from the scene?".format(label)
            ),
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

    def _on_select_in_scene_request(self):
        scene_identifier = self._placeholders_widget.get_selected_identifier()
        if scene_identifier is None:
            return
        result = self._controller.select_placeholder(scene_identifier)
        self._show_action_error(result)
