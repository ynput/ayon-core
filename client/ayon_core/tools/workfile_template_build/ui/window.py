"""Main window of workfile template builder tool."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources, style
from ayon_core.ui.components import AYButton, AYContainer

from ..abstract import (
    BUILD_CONTEXT_CHANGED_TOPIC,
    PLACEHOLDERS_REFRESHED_TOPIC,
    AbstractTemplateBuilderController,
    ActionResult,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from .build_report import BuildReportDialog
from .context_bar import ContextBarWidget
from .editor_widget import (
    OPTIONS_CONTENT_OBJECT_NAME,
    OPTIONS_SCROLL_OBJECT_NAME,
    PlaceholderEditorWidget,
)
from .guide_widget import PlaceholderGuideWidget
from .placeholders_widget import PlaceholdersWidget
from .utils import (
    DIVIDER_COLOR,
    INPUT_COLOR,
    PANEL_COLOR,
    get_palette_color,
)

HINT_PAGE = 0
EDITOR_PAGE = 1

SPLITTER_OBJECT_NAME = "WorkfileTemplateBuilderSplitter"
PAGES_OBJECT_NAME = "WorkfileTemplateBuilderPages"
DIVIDER_OBJECT_NAME = "WorkfileTemplateBuilderDivider"

# Margin inside of the panels
PANEL_MARGIN = 10
# Width of the splitter handle between the panels
SPLITTER_HANDLE_WIDTH = 6

# Input widgets of the placeholder options
OPTION_INPUT_TYPES = (
    "QAbstractSpinBox",
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
    "QComboBox",
)


def _get_window_stylesheet() -> str:
    """Rules applied on top of the AYON stylesheet.

    The AYON stylesheet paints every widget with a background color, widgets
    between the panel and the option inputs should show the panel instead.
    Option inputs use the same color as the inputs of the AYON components,
    e.g. the placeholders filter. Separators of the options are as thin as
    the divider below the context bar.

    Returns:
        str: Stylesheet.

    """
    content = "#{}".format(OPTIONS_CONTENT_OBJECT_NAME)
    inputs_selector = ",\n".join(
        "{} {}".format(content, widget_type)
        for widget_type in OPTION_INPUT_TYPES
    )
    disabled_selector = ",\n".join(
        "{} {}:disabled".format(content, widget_type)
        for widget_type in OPTION_INPUT_TYPES
    )
    return """
#{splitter},
#{pages},
#{scroll},
#{scroll} > QWidget,
{content} {{
    background: transparent;
}}
#{divider},
{content} #Separator {{
    background: {divider_color};
}}
{content} #Separator {{
    min-height: 1px;
    max-height: 1px;
}}
{inputs_selector} {{
    background: {input_color};
}}
{disabled_selector} {{
    background: {panel_color};
}}
""".format(
        splitter=SPLITTER_OBJECT_NAME,
        pages=PAGES_OBJECT_NAME,
        scroll=OPTIONS_SCROLL_OBJECT_NAME,
        content=content,
        divider=DIVIDER_OBJECT_NAME,
        divider_color=get_palette_color(DIVIDER_COLOR),
        inputs_selector=inputs_selector,
        input_color=get_palette_color(INPUT_COLOR),
        disabled_selector=disabled_selector,
        panel_color=get_palette_color(PANEL_COLOR),
    )


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
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
        )

        self.setWindowTitle("AYON Workfile Template Builder - {}".format(
            controller.get_host_name()
        ))
        self.setWindowIcon(QtGui.QIcon(resources.get_ayon_icon_filepath()))
        self.setObjectName("WorkfileTemplateBuilderWindow")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        # --- Workfile and context ---
        context_bar = ContextBarWidget(PANEL_MARGIN, self)
        divider_widget = QtWidgets.QWidget(self)
        divider_widget.setObjectName(DIVIDER_OBJECT_NAME)
        divider_widget.setFixedHeight(1)

        # --- Placeholders panel ---
        placeholders_panel = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_margin=PANEL_MARGIN,
            layout_spacing=8,
        )
        placeholders_widget = PlaceholdersWidget(placeholders_panel)
        build_status_btn = AYButton(
            "",
            parent=placeholders_panel,
            variant=AYButton.Variants.Text,
            icon="description",
        )
        build_status_btn.setVisible(False)
        placeholders_panel.add_widget(placeholders_widget, stretch=1)
        placeholders_panel.layout().addWidget(
            build_status_btn, 0, QtCore.Qt.AlignLeft
        )

        # --- Editor panel ---
        editor_panel = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_margin=PANEL_MARGIN,
        )
        pages_widget = QtWidgets.QStackedWidget(editor_panel)
        pages_widget.setObjectName(PAGES_OBJECT_NAME)
        hint_widget = PlaceholderGuideWidget(pages_widget)
        editor_widget = PlaceholderEditorWidget(controller, pages_widget)
        # The guide has no left margin, so its arrow gets closer to the
        #   "Add" button. The editor keeps the margin of the panel.
        editor_panel.layout().setContentsMargins(
            0, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN
        )
        editor_widget.setContentsMargins(PANEL_MARGIN, 0, 0, 0)
        pages_widget.addWidget(hint_widget)
        pages_widget.addWidget(editor_widget)
        editor_panel.add_widget(pages_widget, stretch=1)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.setObjectName(SPLITTER_OBJECT_NAME)
        splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(placeholders_panel)
        splitter.addWidget(editor_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 680])

        self.add_widget(context_bar)
        self.add_widget(divider_widget)
        self.add_widget(splitter, stretch=1)

        context_bar.context_change_requested.connect(
            self._on_context_change_request
        )
        context_bar.context_reset_requested.connect(
            self._on_context_reset_request
        )
        context_bar.test_build_requested.connect(
            self._on_run_template_build_request
        )
        context_bar.open_template_requested.connect(
            self._on_open_template_request
        )
        context_bar.build_from_template_requested.connect(
            self._on_build_from_template_request
        )
        placeholders_widget.selection_changed.connect(
            self._on_selection_change
        )
        placeholders_widget.create_requested.connect(self._on_create_request)
        placeholders_widget.select_in_scene_requested.connect(
            self._on_select_in_scene_request
        )
        placeholders_widget.refresh_requested.connect(self._on_refresh_request)
        pages_widget.currentChanged.connect(self._update_add_highlight)
        editor_widget.create_requested.connect(self._on_create_confirmed)
        editor_widget.save_requested.connect(self._on_save_confirmed)
        editor_widget.cancel_requested.connect(self._on_create_cancelled)
        editor_widget.run_requested.connect(self._on_run_request)
        editor_widget.remove_requested.connect(self._on_remove_request)
        editor_widget.select_in_scene_requested.connect(
            self._on_select_in_scene_request
        )
        editor_widget.unsaved_changes_changed.connect(
            self._on_unsaved_changes_change
        )
        build_status_btn.clicked.connect(self._on_show_build_report)

        controller.register_event_callback(
            PLACEHOLDERS_REFRESHED_TOPIC, self._on_placeholders_refreshed
        )
        controller.register_event_callback(
            BUILD_CONTEXT_CHANGED_TOPIC, self._on_build_context_changed
        )

        self._controller = controller
        self._context_bar = context_bar
        self._placeholders_widget = placeholders_widget
        self._pages_widget = pages_widget
        self._hint_widget = hint_widget
        self._editor_widget = editor_widget
        self._build_status_btn = build_status_btn

        self._first_show = True
        self._ignore_selection_change = False
        self._current_identifier: Optional[str] = None
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._placeholder_items_by_id: dict[str, PlaceholderItemInfo] = {}

        self._update_build_state()
        self._update_build_context()
        self.resize(1000, 680)

    # --- Qt overrides -------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(
                style.load_stylesheet() + _get_window_stylesheet()
            )
            self.refresh()

    # --- Public API ---------------------------------------------------
    def refresh(self):
        """Collect placeholders from the scene and update the UI."""
        self._controller.reset()

    def select_placeholder(self, scene_identifier: str) -> bool:
        """Select a placeholder and show its options.

        Hosts can use it to show the placeholder that is selected in the
        scene when the tool is opened.

        Args:
            scene_identifier (str): Scene identifier of the placeholder.

        Returns:
            bool: Placeholder was found and selected.

        """
        if scene_identifier not in self._placeholder_items_by_id:
            return False
        self._placeholders_widget.select_identifier(scene_identifier)
        return self._current_identifier == scene_identifier

    # --- Implementation -----------------------------------------------
    def _on_placeholders_refreshed(self):
        self._context_bar.set_workfile(
            self._controller.get_workfile_name(),
            self._controller.get_host_name(),
        )
        self._update_template_path()
        self._update_placeholders()

    def _on_build_context_changed(self):
        self._update_build_context()
        if self._pages_widget.currentIndex() == EDITOR_PAGE:
            self._editor_widget.refresh_preview()

    def _update_build_context(self):
        context_item = self._controller.get_build_context()
        self._context_bar.set_build_context(context_item)
        self._context_bar.set_context_enabled(
            self._controller.is_builder_available()
        )
        self._editor_widget.set_build_context_label(context_item.label)
        self._update_template_path()

    def _update_template_path(self):
        self._context_bar.set_template_path(
            self._controller.get_template_path()
        )

    def _update_placeholders(self):
        self._plugin_items = self._controller.get_placeholder_plugin_items()
        placeholder_items = self._controller.get_placeholder_items()
        self._placeholder_items_by_id = {
            item.scene_identifier: item for item in placeholder_items
        }
        self._update_build_state()

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

    def _update_build_state(self):
        """Enable building only when the host supports it and there is
        something to build."""
        self._context_bar.set_test_build_enabled(
            bool(self._placeholder_items_by_id)
            and self._controller.is_builder_available()
        )

    def _update_hint_message(self):
        if not self._controller.is_builder_available():
            self._hint_widget.set_unavailable(
                "Template build is not available",
                (
                    "Host \"{}\" does not implement workfile template"
                    " build.".format(self._controller.get_host_name())
                ),
            )
            return

        if not self._plugin_items:
            self._hint_widget.set_unavailable(
                "No placeholder types available",
                (
                    "Host \"{}\" does not have any placeholder plugins"
                    " registered.".format(self._controller.get_host_name())
                ),
            )
            return

        self._hint_widget.set_guide(bool(self._placeholder_items_by_id))
        self._update_add_highlight()

    def _update_add_highlight(self):
        """Highlight "Add" while the guide points at it."""
        self._placeholders_widget.set_add_highlighted(
            self._pages_widget.currentIndex() == HINT_PAGE
            and not self._placeholder_items_by_id
        )

    def _show_hint_page(self):
        self._current_identifier = None
        self._set_pending_item(None)
        self._update_hint_message()
        self._pages_widget.setCurrentIndex(HINT_PAGE)

    def _get_plugin_item(
        self, plugin_identifier: Optional[str]
    ) -> Optional[PlaceholderPluginItem]:
        for plugin_item in self._plugin_items:
            if plugin_item.identifier == plugin_identifier:
                return plugin_item
        return None

    def _show_editor_page(self, scene_identifier):
        placeholder_item = self._placeholder_items_by_id.get(scene_identifier)
        if placeholder_item is None:
            self._show_hint_page()
            return

        plugin_item = self._get_plugin_item(placeholder_item.plugin_identifier)
        self._current_identifier = scene_identifier
        self._set_pending_item(None)
        self._editor_widget.set_edit_mode(
            placeholder_item,
            select_supported=(
                plugin_item is not None and plugin_item.select_supported
            ),
        )
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)

    def _show_create_page(self, plugin_item: PlaceholderPluginItem):
        self._current_identifier = None
        self._set_pending_item(plugin_item)
        self._editor_widget.set_create_mode(plugin_item)
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)

    def _set_pending_item(
        self, plugin_item: Optional[PlaceholderPluginItem]
    ) -> None:
        """Show the placeholder that is being created in the list."""
        self._ignore_selection_change = True
        self._placeholders_widget.set_pending_item(plugin_item)
        self._ignore_selection_change = False

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

    def _on_run_template_build_request(self):
        if (
            self._pages_widget.currentIndex() == EDITOR_PAGE
            and self._editor_widget.has_unsaved_changes()
        ):
            QtWidgets.QMessageBox.information(
                self,
                "Unsaved changes",
                (
                    "Save or revert the placeholder changes before building"
                    " the template."
                ),
            )
            return

        context_label = self._controller.get_build_context().label
        answer = QtWidgets.QMessageBox.question(
            self,
            "Run all placeholders?",
            (
                "This will populate all placeholders in the current scene"
                " for {}.\nDo you want to continue?".format(context_label)
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        result = self._controller.run_template_build()

        # Placeholders may have been removed or changed by the build.
        self._update_placeholders()
        self._update_build_status(result)

        # Show a dialog only when the build itself could not run, per
        #   placeholder failures are shown next to the build button.
        has_results = bool(self._controller.get_last_build_results())
        if not result.success and not has_results:
            self._show_action_error(result)

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

        self._show_action_error(self._controller.open_template())

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

        self._show_action_error(self._controller.build_template())

    def _update_build_status(self, result: ActionResult) -> None:
        """Show the outcome of the last template build.

        Args:
            result (ActionResult): Result of the build action.

        """
        results = self._controller.get_last_build_results()
        if not results:
            self._build_status_btn.setVisible(False)
            return

        failed = [entry for entry in results if entry[2]]
        if failed:
            text = "{} of {} failed".format(len(failed), len(results))
            icon = "error"
        else:
            text = "{} populated".format(len(results))
            icon = "check_circle"

        details = []
        for identifier, label, error in results:
            status = "FAILED" if error else "OK"
            details.append("[{}] {} ({})".format(status, label, identifier))
            if error:
                details.append(error)
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
        self._controller.set_build_context(folder_path, task_name)

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
        dialog.setWindowTitle("Preview as")
        dialog.set_context(self._controller.get_project_name())
        if not dialog.exec_():
            return None

        context = dialog.get_context()
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
        dialog = BuildReportDialog(self._controller, parent=self)
        dialog.exec_()

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
                    "Save or revert the placeholder changes before running"
                    " the placeholder."
                ),
            )
            return

        result = self._controller.run_placeholder(scene_identifier)
        if self._show_action_error(result):
            return

        # The placeholder may have been removed by running it.
        self._update_placeholders()

    def _on_remove_request(self, scene_identifier=None):
        if scene_identifier is None:
            scene_identifier = (
                self._placeholders_widget.get_selected_identifier()
            )
        if scene_identifier is None:
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
