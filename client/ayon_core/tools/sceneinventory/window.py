import os
from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core import style, resources
from ayon_core.pipeline import get_current_host_name
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    restore_tool_window_state,
    save_tool_window_state,
)
from ayon_core.tools.utils.overlay_messages import MessageOverlayObject
from ayon_core.tools.sceneinventory import SceneInventoryController

from .view import SceneInventoryView

class SceneInventoryWindow(QtWidgets.QDialog):
    """Scene Inventory window"""

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)

        if controller is None:
            controller = SceneInventoryController()

        overlay_object = MessageOverlayObject(self)
        project_name = controller.get_current_project_name()
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        # Set window title with application name and project name
        base_title = "AYON Scene Inventory"
        app_name = (
            os.environ.get("AYON_APP_NAME")
            or get_current_host_name()
        )
        if app_name:
            window_title = f"{base_title} - {app_name} - {project_name}"
        else:
            window_title = f"{base_title} - {project_name}"
        self.setWindowTitle(window_title)
        self.setObjectName("SceneInventory")

        self.resize(1100, 480)

        filter_label = QtWidgets.QLabel("Search", self)
        text_filter = PlaceholderLineEdit(self)
        text_filter.setPlaceholderText("Filter by name...")

        outdated_only_checkbox = QtWidgets.QCheckBox(
            "Filter to outdated", self
        )
        outdated_only_checkbox.setToolTip("Show outdated files only")
        outdated_only_checkbox.setChecked(False)

        grouping_checkbox = QtWidgets.QCheckBox(
            "Enable grouping", self
        )
        grouping_checkbox.setToolTip("Group items by product group")
        grouping_checkbox.setChecked(True)

        update_all_icon = qtawesome.icon("fa.arrow-up", color="white")
        update_all_button = QtWidgets.QPushButton(self)
        update_all_button.setToolTip("Update all outdated to latest version")
        update_all_button.setIcon(update_all_icon)

        refresh_icon = qtawesome.icon("fa.refresh", color="white")
        refresh_button = QtWidgets.QPushButton(self)
        refresh_button.setToolTip("Refresh")
        refresh_button.setIcon(refresh_icon)

        headers_widget = QtWidgets.QWidget(self)
        headers_layout = QtWidgets.QHBoxLayout(headers_widget)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        headers_layout.addWidget(filter_label, 0)
        headers_layout.addWidget(text_filter, 1)
        headers_layout.addWidget(outdated_only_checkbox, 0)
        headers_layout.addWidget(grouping_checkbox, 0)
        headers_layout.addWidget(update_all_button, 0)
        headers_layout.addWidget(refresh_button, 0)

        view = SceneInventoryView(controller, self)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(headers_widget, 0)
        main_layout.addWidget(view, 1)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(0)
        show_timer.setSingleShot(False)

        # signals
        show_timer.timeout.connect(self._on_show_timer)
        text_filter.textChanged.connect(self._on_text_filter_change)
        outdated_only_checkbox.stateChanged.connect(
            self._on_outdated_state_change
        )
        grouping_checkbox.stateChanged.connect(
            self._on_grouping_state_change
        )
        view.hierarchy_view_changed.connect(
            self._on_hierarchy_view_change
        )
        view.data_changed.connect(self._on_refresh_request)
        refresh_button.clicked.connect(self._on_refresh_request)
        update_all_button.clicked.connect(self._on_update_all)

        self._show_timer = show_timer
        self._show_counter = 0
        self._controller = controller
        self._overlay_object = overlay_object
        self._update_all_button = update_all_button
        self._outdated_only_checkbox = outdated_only_checkbox
        self._grouping_checkbox = grouping_checkbox
        self._view = view

        self._first_show = True

        # Register event callbacks for load notifications
        controller.register_event_callback("load.started", self._on_load_started)
        controller.register_event_callback("load.finished", self._on_load_finished)
        # Register event callbacks for update notifications
        controller.register_event_callback("update.started", self._on_update_started)
        controller.register_event_callback("update.progress", self._on_update_progress)
        controller.register_event_callback("update.finished", self._on_update_finished)
        # Register event callbacks for remove notifications
        controller.register_event_callback("remove.started", self._on_remove_started)
        controller.register_event_callback("remove.progress", self._on_remove_progress)
        controller.register_event_callback("remove.finished", self._on_remove_finished)
        # Register event callbacks for inventory action notifications
        controller.register_event_callback("inventory_action.started", self._on_inventory_action_started)
        controller.register_event_callback("inventory_action.finished", self._on_inventory_action_finished)

    def showEvent(self, event):
        super(SceneInventoryWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            restore_tool_window_state("scene_inventory", self)
            self.setStyleSheet(style.load_stylesheet())

        self._show_counter = 0
        self._show_timer.start()

    def closeEvent(self, event):
        save_tool_window_state("scene_inventory", self)
        super(SceneInventoryWindow, self).closeEvent(event)

    def keyPressEvent(self, event):
        """Custom keyPressEvent.

        Override keyPressEvent to do nothing so that Maya's panels won't
        take focus when pressing "SHIFT" whilst mouse is over viewport or
        outliner. This way users don't accidentally perform Maya commands
        whilst trying to name an instance.

        """
        pass

    def _on_refresh_request(self):
        """Signal callback to trigger 'refresh' without any arguments."""

        self.refresh()

    def refresh(self):
        self._controller.reset()
        self._view.refresh()

    def _on_show_timer(self):
        if self._show_counter < 3:
            self._show_counter += 1
            return
        self._show_timer.stop()
        self.refresh()

    def _on_hierarchy_view_change(self, enabled):
        self._view.set_hierarchy_view(enabled)

    def _on_text_filter_change(self, text_filter):
        self._view.set_text_filter(text_filter)

    def _on_outdated_state_change(self):
        self._view.set_filter_outdated(
            self._outdated_only_checkbox.isChecked()
        )

    def _on_grouping_state_change(self):
        self._view.set_enable_grouping(
            self._grouping_checkbox.isChecked()
        )

    def _on_update_all(self):
        self._view.update_all()

    def _on_load_started(self, event):
        """Handle load.started event and show toast notification."""
        message = event.get("message")
        if message:
            self._overlay_object.add_message(message, message_id=event["id"])
        else:
            # Fallback message if loader doesn't provide one
            self._overlay_object.add_message("Loading...", message_id=event["id"])

    def _on_load_finished(self, event):
        """Handle load.finished event and show completion/error notification."""
        error_info = event["error_info"]
        if not error_info:
            # Show completion message if load was successful
            self._overlay_object.add_message(
                "Action completed successfully",
                message_id=event["id"]
            )
        else:
            # Show error message if load failed
            self._overlay_object.add_message(
                "Action failed",
                "error",
                message_id=event["id"]
            )

    def _on_update_started(self, event):
        """Handle update.started event and show toast notification with progress."""
        message_id = event.get("id")
        message = event.get("message", "Updating containers...")

        if message_id:
            self._overlay_object.add_message(
                message, message_id=message_id
            )
            self._overlay_object.set_progress_visible(
                message_id, True
            )

    def _on_update_progress(self, event):
        """Handle update.progress event to update progress bar."""
        message_id = event.get("id")
        progress = event.get("progress", 0)
        message = event.get("message", "")

        if message_id:
            display_message = (
                f"{message} ({progress}%)"
                if message
                else f"Progress: {progress}%"
            )
            self._overlay_object.update_progress(
                message_id, progress, display_message
            )

    def _on_update_finished(self, event):
        """Handle update.finished event and show completion/error notification."""
        message_id = event.get("id")
        if message_id:
            self._overlay_object.set_progress_visible(
                message_id, False
            )

        if event.get("failed"):
            self._overlay_object.add_message(
                "Failed to update container(s)", "error", message_id=message_id
            )
        else:
            self._overlay_object.add_message(
                "Container(s) updated", message_id=message_id
            )

    def _on_remove_started(self, event):
        """Handle remove.started event and show toast notification."""
        message_id = event.get("id")
        message = event.get("message", "Removing items...")
        total = event.get("total", 0)

        if message_id:
            self._overlay_object.add_message(
                message, message_id=message_id
            )
            # Show progress bar for batch removals
            if total > 1:
                self._overlay_object.set_progress_visible(
                    message_id, True
                )

    def _on_remove_progress(self, event):
        """Handle remove.progress event to update progress bar."""
        message_id = event.get("id")
        progress = event.get("progress", 0)
        message = event.get("message", "")

        if message_id:
            display_message = (
                f"{message} ({progress}%)"
                if message
                else f"Progress: {progress}%"
            )
            self._overlay_object.update_progress(
                message_id, progress, display_message
            )

    def _on_remove_finished(self, event):
        """Handle remove.finished event and show completion/error notification."""
        message_id = event.get("id")
        if message_id:
            self._overlay_object.set_progress_visible(
                message_id, False
            )

        if event.get("failed"):
            self._overlay_object.add_message(
                "Failed to remove item(s)", "error", message_id=message_id
            )
        else:
            self._overlay_object.add_message(
                "Item(s) removed", message_id=message_id
            )

    def _on_inventory_action_started(self, event):
        """Handle inventory_action.started event and show toast notification."""
        message_id = event.get("id")
        message = event.get("message", "Running action...")

        if message_id:
            self._overlay_object.add_message(
                message, message_id=message_id
            )

    def _on_inventory_action_finished(self, event):
        """Handle inventory_action.finished event and show completion/error notification."""
        message_id = event.get("id")

        if event.get("failed"):
            self._overlay_object.add_message(
                "Action failed", "error", message_id=message_id
            )
        else:
            self._overlay_object.add_message(
                "Action completed", message_id=message_id
            )
